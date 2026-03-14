import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from backend.services.metric_collector import subscribe, unsubscribe
from backend.utils.security import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/monitor/{conn_id}")
async def monitor_websocket(websocket: WebSocket, conn_id: int, token: str = Query(default=None)):
    # Validate token for WebSocket connections
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    try:
        payload = decode_access_token(token)
        if not payload.get("sub"):
            await websocket.close(code=1008, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    queue = subscribe(conn_id)
    logger.info(f"WebSocket client connected for connection {conn_id}")

    # Immediately send the latest metric snapshot to avoid waiting for next collection cycle
    try:
        from backend.database import async_session
        from backend.models.metric_snapshot import MetricSnapshot
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.datasource_id == conn_id, MetricSnapshot.metric_type == "db_status")
                .order_by(MetricSnapshot.collected_at.desc())
                .limit(1)
            )
            latest_snapshot = result.scalar_one_or_none()

            if latest_snapshot:
                await websocket.send_json({
                    "type": "db_status",
                    "datasource_id": conn_id,
                    "data": latest_snapshot.data,
                    "collected_at": latest_snapshot.collected_at.isoformat(),
                })
                logger.info(f"Sent latest snapshot to WebSocket client for connection {conn_id}")
    except Exception as e:
        logger.warning(f"Failed to send initial snapshot: {e}")

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(data)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
            except Exception as e:
                logger.error(f"Error sending metric: {e}")
                break
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(conn_id, queue)
        logger.info(f"WebSocket client disconnected for connection {conn_id}")
