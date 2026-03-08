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

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Hub for pushing metrics to WebSocket clients
_metric_subscribers: Dict[int, List[asyncio.Queue]] = {}

# AI Guardian components (lazy loaded)
_anomaly_detector = None
_importance_classifier = None


def _get_anomaly_detector():
    """Lazy load anomaly detector"""
    global _anomaly_detector
    if _anomaly_detector is None:
        from backend.services.anomaly_detector import AnomalyDetector
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector


def _get_importance_classifier():
    """Lazy load importance classifier"""
    global _importance_classifier
    if _importance_classifier is None:
        from backend.services.importance_classifier import ImportanceClassifier
        _importance_classifier = ImportanceClassifier()
    return _importance_classifier


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
            if datasource.ssh_host_id:
                os_metrics = await _collect_os_metrics(db, datasource.ssh_host_id)
                if os_metrics:
                    normalized_status.update(os_metrics)

            snapshot = MetricSnapshot(
                datasource_id=datasource_id,
                metric_type="db_status",
                data=normalized_status,
            )
            db.add(snapshot)
            await db.commit()

            # Push to WebSocket subscribers
            await _push_to_subscribers(datasource_id, {
                "type": "db_status",
                "datasource_id": datasource_id,
                "data": normalized_status,
                "collected_at": datetime.utcnow().isoformat(),
            })

            # AI Guardian: 异常检测
            await _detect_anomalies(db, datasource_id, normalized_status)

            await connector.close()

    except Exception as e:
        logger.error(f"Error collecting metrics for datasource {datasource_id}: {e}")


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


async def _collect_os_metrics(db, ssh_host_id: int) -> Dict[str, Any]:
    """采集操作系统指标"""
    try:
        from sqlalchemy import select
        from backend.models.ssh_host import SSHHost
        from backend.utils.encryption import decrypt_value
        from backend.services.os_metrics_collector import OSMetricsCollector
        import paramiko

        # 获取 SSH 主机配置
        result = await db.execute(
            select(SSHHost).where(SSHHost.id == ssh_host_id)
        )
        ssh_host = result.scalar_one_or_none()
        if not ssh_host:
            return {}

        # 创建 SSH 连接
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if ssh_host.auth_type == 'password':
                password = decrypt_value(ssh_host.password_encrypted) if ssh_host.password_encrypted else None
                ssh_client.connect(
                    hostname=ssh_host.host,
                    port=ssh_host.port,
                    username=ssh_host.username,
                    password=password,
                    timeout=10
                )
            else:
                # 密钥认证
                private_key_str = decrypt_value(ssh_host.private_key_encrypted) if ssh_host.private_key_encrypted else None
                if private_key_str:
                    from io import StringIO
                    key_file = StringIO(private_key_str)
                    private_key = paramiko.RSAKey.from_private_key(key_file)
                    ssh_client.connect(
                        hostname=ssh_host.host,
                        port=ssh_host.port,
                        username=ssh_host.username,
                        pkey=private_key,
                        timeout=10
                    )

            # 采集 OS 指标
            os_metrics = await OSMetricsCollector.collect_via_ssh(ssh_client, os_type='linux')
            ssh_client.close()

            return os_metrics

        except Exception as e:
            logger.warning(f"Failed to collect OS metrics via SSH {ssh_host_id}: {e}")
            ssh_client.close()
            return {}

    except Exception as e:
        logger.error(f"Error in _collect_os_metrics: {e}")
        return {}


async def _detect_anomalies(db, datasource_id: int, status: Dict[str, Any]):
    """AI Guardian: 检测异常"""
    try:
        # 获取重要性评分
        importance_classifier = _get_importance_classifier()
        importance = await importance_classifier.get_importance(db, datasource_id)

        # 对所有级别进行异常检测（调整后）
        # CRITICAL/IMPORTANT: 实时检测所有指标
        # NORMAL: 检测关键指标（connections, qps, tps）
        anomaly_detector = _get_anomaly_detector()

        # 根据重要性级别选择检测指标
        if importance and importance.importance_tier in ['CRITICAL', 'IMPORTANT']:
            # 检测所有关键指标（包括 OS 指标）
            metrics_to_check = {
                'cpu_usage': status.get('cpu_usage'),
                'memory_usage': status.get('memory_usage'),
                'disk_usage': status.get('disk_usage'),
                'connections': status.get('connections'),
                'qps': status.get('qps'),
                'tps': status.get('tps'),
                'load_avg_1min': status.get('load_avg_1min'),
                'load_avg_5min': status.get('load_avg_5min'),
                'disk_reads_per_sec': status.get('disk_reads_per_sec'),
                'disk_writes_per_sec': status.get('disk_writes_per_sec'),
            }
        else:
            # NORMAL 级别：检测数据库指标 + 关键 OS 指标
            metrics_to_check = {
                'connections': status.get('connections'),
                'qps': status.get('qps'),
                'tps': status.get('tps'),
                'cpu_usage': status.get('cpu_usage'),
                'memory_usage': status.get('memory_usage'),
            }

        for metric_name, value in metrics_to_check.items():
            if value is not None:
                try:
                    anomaly = await anomaly_detector.detect_and_record(
                        db, datasource_id, metric_name, value, status
                    )

                    if anomaly:
                        # 如果是 CRITICAL 且启用自动修复，触发主动诊断
                        if importance and importance.importance_tier == 'CRITICAL' and importance.auto_fix_enabled:
                            # TODO: 触发主动诊断（Phase 3）
                            logger.info(f"Anomaly detected for CRITICAL datasource {datasource_id}, "
                                      f"proactive diagnosis will be triggered in Phase 3")
                except Exception as e:
                    logger.error(f"Error detecting anomaly for {metric_name}: {e}")

    except Exception as e:
        logger.error(f"Error in anomaly detection for datasource {datasource_id}: {e}")


