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
