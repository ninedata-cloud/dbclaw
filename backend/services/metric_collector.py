import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_, desc

from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.alert_message import AlertMessage
from backend.services.db_connector import get_connector
from backend.utils.encryption import decrypt_value
from backend.services.threshold_checker import ThresholdChecker
from backend.utils.datetime_helper import now
from backend.config import get_settings

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
    try:
        async with async_session() as db:
                result = await db.execute(
                    select(Datasource).where(Datasource.id == datasource_id, Datasource.is_active == True)
                )
                datasource = result.scalar_one_or_none()
                if not datasource:
                    return

                # 检查是否在静默期内，如果是则跳过采集
                if datasource.silence_until:
                    current_time = now()
                    if current_time < datasource.silence_until:
                        logger.debug(f"Skipping metrics collection for datasource {datasource_id}: in silence period until {datasource.silence_until}")
                        return
                    else:
                        # 静默已过期，自动清除
                        datasource.silence_until = None
                        datasource.silence_reason = None
                        await db.commit()
                        logger.info(f"Silence period expired for datasource {datasource_id}, resuming monitoring")

                password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
                connector = get_connector(
                    db_type=datasource.db_type,
                    host=datasource.host,
                    port=datasource.port,
                    username=datasource.username,
                    password=password,
                    database=datasource.database,
                    extra_params=datasource.extra_params,
                )

                try:
                    status = await connector.get_status()
                    connection_failed = False

                    # Auto-resolve connection failure alerts if connection is now successful
                    await _auto_resolve_connection_alerts(db, datasource_id)

                except Exception as e:
                    logger.warning(f"Failed to collect metrics for datasource {datasource_id}: {e}")
                    status = {"error": str(e), "connection_failed": True}
                    connection_failed = True

                # 标准化指标
                from backend.services.metric_normalizer import MetricNormalizer
                normalized_status = MetricNormalizer.normalize(
                    datasource.db_type, datasource_id, status
                )

                # 采集 OS 指标（如果配置了 SSH）
                if datasource.host_id:
                    try:
                        # 使用超时保护，避免SSH连接挂起导致长时间阻塞
                        os_metrics = await asyncio.wait_for(
                            _collect_os_metrics(db, datasource.host_id),
                            timeout=30.0  # 30秒超时
                        )
                        if os_metrics:
                            # 所有数据库统一使用 SSH 采集的 OS 指标
                            # 直接使用 OS 指标，覆盖数据库层面的同名指标（如果有）
                            normalized_status.update(os_metrics)
                    except asyncio.TimeoutError:
                        logger.warning(f"SSH metrics collection timeout for datasource {datasource_id} (host_id={datasource.host_id})")
                    except Exception as e:
                        logger.warning(f"Failed to collect SSH metrics for datasource {datasource_id}: {e}")

                # 使用信号量保护数据库写入
                async with _db_write_semaphore:
                    snapshot = MetricSnapshot(
                        datasource_id=datasource_id,
                        metric_type="db_status",
                        data=normalized_status,
                        collected_at=now(),  # 使用本地时间
                    )
                    db.add(snapshot)
                    await db.commit()

                # Handle connection failure - create alert and trigger diagnosis
                if connection_failed:
                    await _handle_connection_failure(db, datasource_id, datasource, status.get("error", "Unknown error"))

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


async def _auto_resolve_connection_alerts(db, datasource_id: int):
    """
    Auto-resolve connection failure alerts when connection is restored.

    Args:
        db: Database session
        datasource_id: Datasource ID
    """
    try:
        # Get all active system_error alerts for connection failures
        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.datasource_id == datasource_id,
                    AlertMessage.alert_type == "system_error",
                    AlertMessage.metric_name == "connection_status",
                    AlertMessage.status.in_(["active", "acknowledged"])
                )
            )
        )
        connection_alerts = result.scalars().all()

        if not connection_alerts:
            return

        # Resolve all connection failure alerts
        from backend.services.alert_service import AlertService
        for alert in connection_alerts:
            await AlertService.resolve_alert(db, alert.id)
            logger.info(f"Auto-resolved connection failure alert {alert.id}: connection restored")

    except Exception as e:
        logger.error(f"Error auto-resolving connection alerts for datasource {datasource_id}: {e}", exc_info=True)


async def _auto_resolve_recovered_alerts(
    db,
    datasource_id: int,
    metrics: Dict[str, Any],
    threshold_rules: Dict[str, Any],
    current_violations: List[Dict[str, Any]]
):
    """
    Auto-resolve alerts for metrics that have recovered to normal levels.

    Args:
        db: Database session
        datasource_id: Datasource ID
        metrics: Current metric values
        threshold_rules: Configured threshold rules
        current_violations: List of current violations (to avoid resolving alerts that are still active)
    """
    try:
        # Get all active threshold_violation alerts for this datasource
        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.datasource_id == datasource_id,
                    AlertMessage.alert_type == "threshold_violation",
                    AlertMessage.status.in_(["active", "acknowledged"])
                )
            )
        )
        active_alerts = result.scalars().all()

        if not active_alerts:
            return

        # Build set of currently violating metrics
        violating_metrics = {v['metric_name'] for v in current_violations}

        # Check each active alert
        for alert in active_alerts:
            if not alert.metric_name:
                continue

            # Skip if this metric is still violating
            if alert.metric_name in violating_metrics:
                continue

            # Get current metric value
            current_value = metrics.get(alert.metric_name)
            if current_value is None:
                continue

            # Find the threshold rule for this metric
            # threshold_rules is a dict like {"cpu_usage": {"threshold": 80, "duration": 60}}
            threshold_rule = threshold_rules.get(alert.metric_name)

            if not threshold_rule:
                continue

            # Check if metric has recovered (is now below threshold)
            threshold = threshold_rule.get('threshold')
            if threshold is None:
                continue

            if current_value < threshold:
                # Metric has recovered - auto-resolve the alert
                from backend.services.alert_service import AlertService
                await AlertService.resolve_alert(db, alert.id, resolved_value=current_value)
                logger.info(
                    f"Auto-resolved alert {alert.id}: {alert.metric_name} recovered "
                    f"(current={current_value:.2f} < threshold={threshold})"
                )

    except Exception as e:
        logger.error(f"Error auto-resolving recovered alerts for datasource {datasource_id}: {e}", exc_info=True)


async def _check_thresholds_and_trigger(db, datasource_id: int, metrics: Dict[str, Any]):
    """Check if metrics violate thresholds and trigger inspection if needed"""
    global _inspection_service, _threshold_checker

    if not _inspection_service:
        return

    try:
        # 检查数据源是否在静默期内
        result = await db.execute(
            select(Datasource).where(Datasource.id == datasource_id)
        )
        datasource = result.scalar_one_or_none()
        if datasource and datasource.silence_until:
            current_time = now()
            if current_time < datasource.silence_until:
                logger.debug(f"Skipping threshold check for datasource {datasource_id}: in silence period")
                return

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

        # Auto-resolve alerts for metrics that have recovered
        await _auto_resolve_recovered_alerts(db, datasource_id, metrics, config.threshold_rules, violations)

        # Trigger inspection and create alert for each violation
        for violation in violations:
            metric_name = violation['metric_name']
            reason = (
                f"{metric_name}={violation['current_value']:.2f} > "
                f"{violation['threshold']} for {violation['violation_duration']:.0f}s"
            )

            # Check if there's a recent anomaly trigger for the same metric
            # to avoid duplicate triggers for ongoing issues
            from backend.services.config_service import get_config as _get_config
            dedup_minutes = await _get_config(db, "inspection_dedup_window_minutes", default=get_settings().inspection_dedup_window_minutes)
            recent_trigger = await db.execute(
                select(InspectionTrigger).where(
                    and_(
                        InspectionTrigger.datasource_id == datasource_id,
                        InspectionTrigger.trigger_type == "anomaly",
                        InspectionTrigger.trigger_reason.like(f"{metric_name}=%"),
                        InspectionTrigger.triggered_at >= now() - timedelta(minutes=dedup_minutes)
                    )
                ).order_by(desc(InspectionTrigger.triggered_at)).limit(1)
            )
            existing_trigger = recent_trigger.scalar_one_or_none()

            if existing_trigger:
                logger.debug(f"Skipping duplicate anomaly trigger for datasource {datasource_id} metric {metric_name} - recent trigger {existing_trigger.id} exists")
                continue

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

            # Create alert for the violation
            from backend.services.alert_service import AlertService

            # Calculate severity based on percentage over threshold
            percent_over = ((violation['current_value'] - violation['threshold']) / violation['threshold']) * 100
            severity = AlertService.calculate_severity(percent_over)

            await AlertService.create_alert(
                db=db,
                datasource_id=datasource_id,
                alert_type="threshold_violation",
                severity=severity,
                metric_name=violation['metric_name'],
                metric_value=violation['current_value'],
                threshold_value=violation['threshold'],
                trigger_reason=reason
            )

    except Exception as e:
        logger.error(f"Error checking thresholds for datasource {datasource_id}: {e}", exc_info=True)


async def _handle_connection_failure(db, datasource_id: int, datasource, error_message: str):
    """Handle database/host connection failure - create alert and trigger diagnosis"""
    global _inspection_service

    try:
        # 检查数据源是否在静默期内
        if datasource.silence_until:
            current_time = now()
            if current_time < datasource.silence_until:
                logger.debug(f"Skipping connection failure alert for datasource {datasource_id}: in silence period")
                return

        from backend.services.alert_service import AlertService

        # Check if there's a recent unprocessed connection_failure trigger
        # to avoid duplicate triggers for the same ongoing issue
        from backend.services.config_service import get_config as _get_config
        dedup_minutes = await _get_config(db, "inspection_dedup_window_minutes", default=get_settings().inspection_dedup_window_minutes)
        recent_trigger = await db.execute(
            select(InspectionTrigger).where(
                and_(
                    InspectionTrigger.datasource_id == datasource_id,
                    InspectionTrigger.trigger_type == "connection_failure",
                    InspectionTrigger.triggered_at >= now() - timedelta(minutes=dedup_minutes)
                )
            ).order_by(desc(InspectionTrigger.triggered_at)).limit(1)
        )
        existing_trigger = recent_trigger.scalar_one_or_none()

        if existing_trigger:
            logger.debug(f"Skipping duplicate connection_failure trigger for datasource {datasource_id} - recent trigger {existing_trigger.id} exists")
            return

        # Create critical alert for connection failure
        alert = await AlertService.create_alert(
            db=db,
            datasource_id=datasource_id,
            alert_type="system_error",
            severity="critical",
            metric_name="connection_status",
            metric_value=0.0,  # 0 = failed
            threshold_value=1.0,  # 1 = expected success
            trigger_reason=f"Connection failed: {error_message}"
        )

        logger.error(f"Connection failure alert created for datasource {datasource_id}: {alert.id}")

        # Trigger AI diagnosis if inspection service is available
        if _inspection_service:
            reason = f"Database connection failed: {datasource.name} ({datasource.db_type})"
            metric_snapshot = {
                "error": error_message,
                "datasource_name": datasource.name,
                "db_type": datasource.db_type,
                "host": datasource.host,
                "port": datasource.port,
                "timestamp": now().isoformat()
            }

            await _inspection_service.trigger_inspection(
                db=db,
                datasource_id=datasource_id,
                trigger_type="connection_failure",
                reason=reason,
                metric_snapshot=metric_snapshot
            )

            logger.info(f"Triggered AI diagnosis for connection failure: datasource {datasource_id}")

    except Exception as e:
        logger.error(f"Error handling connection failure for datasource {datasource_id}: {e}", exc_info=True)


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
    """采集操作系统指标（使用连接池）"""
    try:
        from backend.services.os_metrics_collector import OSMetricsCollector
        from backend.services.ssh_connection_pool import get_ssh_pool

        # 从连接池获取SSH连接
        ssh_pool = get_ssh_pool()

        try:
            async with ssh_pool.get_connection(db, host_id) as ssh_client:
                # 采集 OS 指标
                os_metrics = await OSMetricsCollector.collect_via_ssh(ssh_client, os_type='linux')
                return os_metrics

        except ConnectionError as e:
            logger.warning(f"Failed to get SSH connection for host {host_id}: {e}")
            return {}
        except Exception as e:
            logger.warning(f"Failed to collect OS metrics via SSH {host_id}: {e}")
            return {}

    except Exception as e:
        logger.error(f"Error in _collect_os_metrics: {e}")
        return {}

