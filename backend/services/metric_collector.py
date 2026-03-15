import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.metric_snapshot import MetricSnapshot
from backend.services.db_connector import get_connector
from backend.utils.encryption import decrypt_value
from backend.services.threshold_checker import ThresholdChecker
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Hub for pushing metrics to WebSocket clients
_metric_subscribers: Dict[int, List[asyncio.Queue]] = {}

# Inspection service (set by app.py)
_inspection_service = None

# Threshold checker instance
_threshold_checker = ThresholdChecker()

# Semaphore to limit concurrent database writes
_db_write_semaphore = asyncio.Semaphore(3)  # 最多 3 个并发写入


def set_inspection_service(service):
    """Set the inspection service instance"""
    global _inspection_service
    _inspection_service = service


def subscribe(datasource_id: int) -> asyncio.Queue:
    """Subscribe to real-time metrics for a datasource."""
    queue = asyncio.Queue(maxsize=100)
    _metric_subscribers.setdefault(datasource_id, []).append(queue)
    return queue


def unsubscribe(datasource_id: int, queue: asyncio.Queue):
    """Unsubscribe from real-time metrics."""
    if datasource_id in _metric_subscribers:
        try:
            _metric_subscribers[datasource_id].remove(queue)
        except ValueError:
            pass
        if not _metric_subscribers[datasource_id]:
            del _metric_subscribers[datasource_id]


async def _push_to_subscribers(datasource_id: int, data: Dict[str, Any]):
    """Push metric data to all subscribers of a datasource."""
    if datasource_id not in _metric_subscribers:
        return
    dead_queues = []
    for queue in _metric_subscribers[datasource_id]:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            dead_queues.append(queue)
    for q in dead_queues:
        try:
            _metric_subscribers[datasource_id].remove(q)
        except ValueError:
            pass


async def collect_metrics_for_connection(datasource_id: int):
    """Collect and store metrics for a single datasource."""
    async with _db_write_semaphore:  # 限制并发写入
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Datasource).where(Datasource.id == datasource_id, Datasource.is_active == True)
                )
                datasource = result.scalar_one_or_none()
                if not datasource:
                    return

                password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
                connector = get_connector(
                    db_type=datasource.db_type,
                    host=datasource.host,
                    port=datasource.port,
                    username=datasource.username,
                    password=password,
                    database=datasource.database,
                )

                try:
                    status = await connector.get_status()
                except Exception as e:
                    logger.warning(f"Failed to collect metrics for datasource {datasource_id}: {e}")
                    status = {"error": str(e)}

                # 标准化指标
                from backend.services.metric_normalizer import MetricNormalizer
                normalized_status = MetricNormalizer.normalize(
                    datasource.db_type, datasource_id, status
                )

                # 采集 OS 指标（如果配置了 SSH）
                if datasource.host_id:
                    os_metrics = await _collect_os_metrics(db, datasource.host_id)
                    if os_metrics:
                        normalized_status.update(os_metrics)

                snapshot = MetricSnapshot(
                    datasource_id=datasource_id,
                    metric_type="db_status",
                    data=normalized_status,
                    collected_at=now(),  # 使用本地时间
                )
                db.add(snapshot)
                await db.commit()

                # Check thresholds and trigger inspection if needed
                await _check_thresholds_and_trigger(db, datasource_id, normalized_status)

                # Push to WebSocket subscribers
                await _push_to_subscribers(datasource_id, {
                    "type": "db_status",
                    "datasource_id": datasource_id,
                    "data": normalized_status,
                    "collected_at": now().isoformat(),
                })

                await connector.close()

        except Exception as e:
            logger.error(f"Error collecting metrics for datasource {datasource_id}: {e}")


async def _check_thresholds_and_trigger(db, datasource_id: int, metrics: Dict[str, Any]):
    """Check if metrics violate thresholds and trigger inspection if needed"""
    global _inspection_service, _threshold_checker

    if not _inspection_service:
        return

    try:
        # Get inspection config for this datasource
        from backend.models.inspection_config import InspectionConfig

        result = await db.execute(
            select(InspectionConfig).where(
                InspectionConfig.datasource_id == datasource_id,
                InspectionConfig.enabled == True
            )
        )
        config = result.scalar_one_or_none()

        if not config or not config.threshold_rules:
            return

        # Check thresholds
        violations = _threshold_checker.check_thresholds(
            datasource_id=datasource_id,
            metrics=metrics,
            threshold_rules=config.threshold_rules
        )

        # Trigger inspection for each violation
        for violation in violations:
            reason = (
                f"{violation['metric_name']}={violation['current_value']:.2f} > "
                f"{violation['threshold']} for {violation['violation_duration']:.0f}s"
            )

            logger.info(f"Triggering anomaly inspection for datasource {datasource_id}: {reason}")

            # Create metric snapshot for the trigger
            metric_snapshot = {
                "violation": violation,
                "full_metrics": metrics,
                "timestamp": now().isoformat()
            }

            # Trigger inspection asynchronously
            await _inspection_service.trigger_inspection(
                db=db,
                datasource_id=datasource_id,
                trigger_type="anomaly",
                reason=reason,
                metric_snapshot=metric_snapshot
            )

    except Exception as e:
        logger.error(f"Error checking thresholds for datasource {datasource_id}: {e}", exc_info=True)


async def collect_all_metrics():
    """Collect metrics for all active datasources."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Datasource.id).where(Datasource.is_active == True)
            )
            datasource_ids = [row[0] for row in result.fetchall()]

        tasks = [collect_metrics_for_connection(ds_id) for ds_id in datasource_ids]
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


async def _collect_os_metrics(db, host_id: int) -> Dict[str, Any]:
    """采集操作系统指标"""
    try:
        from sqlalchemy import select
        from backend.models.host import Host
        from backend.utils.encryption import decrypt_value
        from backend.services.os_metrics_collector import OSMetricsCollector
        import paramiko

        # 获取 SSH 主机配置
        result = await db.execute(
            select(Host).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()
        if not host:
            return {}

        # 创建 SSH 连接
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if host.auth_type == 'password':
                password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
                ssh_client.connect(
                    hostname=host.host,
                    port=host.port,
                    username=host.username,
                    password=password,
                    timeout=10
                )
            else:
                # 密钥认证
                private_key_str = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
                if private_key_str:
                    from io import StringIO
                    key_file = StringIO(private_key_str)
                    private_key = paramiko.RSAKey.from_private_key(key_file)
                    ssh_client.connect(
                        hostname=host.host,
                        port=host.port,
                        username=host.username,
                        pkey=private_key,
                        timeout=10
                    )

            # 采集 OS 指标
            os_metrics = await OSMetricsCollector.collect_via_ssh(ssh_client, os_type='linux')
            ssh_client.close()

            return os_metrics

        except Exception as e:
            logger.warning(f"Failed to collect OS metrics via SSH {host_id}: {e}")
            ssh_client.close()
            return {}

    except Exception as e:
        logger.error(f"Error in _collect_os_metrics: {e}")
        return {}

