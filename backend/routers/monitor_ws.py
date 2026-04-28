import asyncio
import logging
from urllib.parse import urlparse
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.config import get_settings
from backend.database import async_session
from backend.models.user import User
from backend.models.soft_delete import alive_filter
from backend.services.config_service import get_config
from backend.services.metric_collector import subscribe, unsubscribe
from backend.services.session_service import SessionService
from backend.utils.datetime_helper import to_utc_isoformat

logger = logging.getLogger(__name__)
router = APIRouter()


async def _validate_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    allowed_host = {websocket.headers.get("host", "")}
    async with async_session() as db:
        external_base_url = await get_config(db, "app_external_base_url", default="")

    if external_base_url:
        parsed = urlparse(external_base_url)
        if parsed.netloc:
            allowed_host.add(parsed.netloc)

    parsed_origin = urlparse(origin)
    return bool(parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc in allowed_host)


async def _authenticate_websocket(websocket: WebSocket) -> User | None:
    session_id = websocket.cookies.get(get_settings().session_cookie_name)
    async with async_session() as db:
        session = await SessionService.get_active_session(db, session_id)
        if not session:
            return None
        result = await db.execute(select(User).where(User.id == session.user_id, alive_filter(User)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        await SessionService.touch_session(db, session)
        await db.commit()
        return user


@router.websocket("/ws/monitor/{conn_id}")
async def monitor_websocket(websocket: WebSocket, conn_id: int):
    if not await _validate_websocket_origin(websocket):
        await websocket.close(code=1008, reason="Invalid origin")
        return

    user = await _authenticate_websocket(websocket)
    if not user:
        await websocket.close(code=1008, reason="Invalid or expired session")
        return

    await websocket.accept()
    queue = subscribe(conn_id)
    logger.info(f"WebSocket client connected for connection {conn_id}, user {user.id}")

    try:
        from backend.models.datasource_metric import DatasourceMetric

        async with async_session() as db:
            result = await db.execute(
                select(DatasourceMetric)
                .where(DatasourceMetric.datasource_id == conn_id, DatasourceMetric.metric_type == "db_status")
                .order_by(DatasourceMetric.id.desc())
                .limit(1)
            )
            latest_snapshot = result.scalar_one_or_none()

            if latest_snapshot:
                await websocket.send_json({
                    "type": "db_status",
                    "datasource_id": conn_id,
                    "data": latest_snapshot.data,
                    "collected_at": to_utc_isoformat(latest_snapshot.collected_at),
                })
                logger.info(f"Sent latest snapshot to WebSocket client for connection {conn_id}")
    except Exception as e:
        logger.warning(f"Failed to send initial snapshot: {e}")

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(data)
            except asyncio.CancelledError:
                # Server shutdown may cancel this task while waiting on queue.get().
                break
            except asyncio.TimeoutError:
                user = await _authenticate_websocket(websocket)
                if not user:
                    await websocket.close(code=1008, reason="Session expired")
                    break
                await websocket.send_json({"type": "heartbeat"})
            except Exception as e:
                logger.error(f"Error sending metric: {e}")
                break
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        # Graceful shutdown path for uvicorn/asyncio cancellation.
        pass
    finally:
        unsubscribe(conn_id, queue)
        logger.info(f"WebSocket client disconnected for connection {conn_id}")
