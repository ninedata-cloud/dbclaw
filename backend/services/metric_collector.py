import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from backend.database import async_session
from backend.models.connection import Connection
from backend.models.metric_snapshot import MetricSnapshot
from backend.services.db_connector import get_connector
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Hub for pushing metrics to WebSocket clients
_metric_subscribers: Dict[int, List[asyncio.Queue]] = {}


def subscribe(conn_id: int) -> asyncio.Queue:
    """Subscribe to real-time metrics for a connection."""
    queue = asyncio.Queue(maxsize=100)
    _metric_subscribers.setdefault(conn_id, []).append(queue)
    return queue


def unsubscribe(conn_id: int, queue: asyncio.Queue):
    """Unsubscribe from real-time metrics."""
    if conn_id in _metric_subscribers:
        try:
            _metric_subscribers[conn_id].remove(queue)
        except ValueError:
            pass
        if not _metric_subscribers[conn_id]:
            del _metric_subscribers[conn_id]


async def _push_to_subscribers(conn_id: int, data: Dict[str, Any]):
    """Push metric data to all subscribers of a connection."""
    if conn_id not in _metric_subscribers:
        return
    dead_queues = []
    for queue in _metric_subscribers[conn_id]:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            dead_queues.append(queue)
    for q in dead_queues:
        try:
            _metric_subscribers[conn_id].remove(q)
        except ValueError:
            pass


async def collect_metrics_for_connection(conn_id: int):
    """Collect and store metrics for a single connection."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Connection).where(Connection.id == conn_id, Connection.is_active == True)
            )
            conn = result.scalar_one_or_none()
            if not conn:
                return

            password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None
            connector = get_connector(
                db_type=conn.db_type,
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )

            try:
                status = await connector.get_status()
            except Exception as e:
                logger.warning(f"Failed to collect metrics for connection {conn_id}: {e}")
                status = {"error": str(e)}

            snapshot = MetricSnapshot(
                connection_id=conn_id,
                metric_type="db_status",
                data=status,
            )
            db.add(snapshot)
            await db.commit()

            # Push to WebSocket subscribers
            await _push_to_subscribers(conn_id, {
                "type": "db_status",
                "connection_id": conn_id,
                "data": status,
                "collected_at": datetime.utcnow().isoformat(),
            })

            await connector.close()

    except Exception as e:
        logger.error(f"Error collecting metrics for connection {conn_id}: {e}")


async def collect_all_metrics():
    """Collect metrics for all active connections."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Connection.id).where(Connection.is_active == True)
            )
            conn_ids = [row[0] for row in result.fetchall()]

        tasks = [collect_metrics_for_connection(cid) for cid in conn_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error in collect_all_metrics: {e}")


def start_scheduler(interval_seconds: int = 15):
    """Start the APScheduler for periodic metric collection."""
    global scheduler
    if scheduler and scheduler.running:
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        collect_all_metrics,
        "interval",
        seconds=interval_seconds,
        id="metric_collector",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Metric collector started (interval: {interval_seconds}s)")


def stop_scheduler():
    """Stop the metric scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Metric collector stopped")
