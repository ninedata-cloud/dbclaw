import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_, desc

from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.alert_message import AlertMessage
from backend.services.db_connector import get_connector
from backend.services.metric_snapshot_merge import (
    cleanup_obsolete_integration_keys,
    merge_system_metric_data_for_integration,
)
from backend.utils.encryption import decrypt_value
from backend.services.threshold_checker import ThresholdChecker
from backend.services.baseline_service import (
    BaselineSignalDetector,
    compute_upper_bound,
    extract_metric_value,
    get_profiles_for_slot,
    normalize_baseline_config,
    refresh_current_slot_profiles,
)
from backend.services.alert_template_service import resolve_effective_inspection_config
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
_baseline_detector = BaselineSignalDetector()

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
    connector = None
    try:
        async with async_session() as db:
                result = await db.execute(
                    select(Datasource).where(Datasource.id == datasource_id, Datasource.is_active == True, alive_filter(Datasource))
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
                    datasource.connection_status = "normal"
                    datasource.connection_error = None
                    datasource.connection_checked_at = now()

                    # Auto-resolve connection failure alerts if connection is now successful
                    await _auto_resolve_connection_alerts(db, datasource_id)

                except Exception as e:
                    logger.warning(f"Failed to collect metrics for datasource {datasource_id}: {e}")
                    status = {"error": str(e), "connection_failed": True}
                    connection_failed = True
                    datasource.connection_status = "failed"
                    datasource.connection_error = str(e)
                    datasource.connection_checked_at = now()

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

                snapshot_data = normalized_status
                if datasource.metric_source == "integration":
                    latest_result = await db.execute(
                        select(MetricSnapshot)
                        .where(
                            MetricSnapshot.datasource_id == datasource_id,
                            MetricSnapshot.metric_type == "db_status",
                        )
                        .order_by(desc(MetricSnapshot.collected_at))
                        .limit(1)
                    )
                    latest_snapshot = latest_result.scalar_one_or_none()
                    snapshot_data = merge_system_metric_data_for_integration(
                        latest_snapshot.data if latest_snapshot and latest_snapshot.data else {},
                        normalized_status,
                    )
                    snapshot_data = cleanup_obsolete_integration_keys(datasource.db_type, snapshot_data)

                # 使用信号量保护数据库写入
                async with _db_write_semaphore:
                    snapshot = MetricSnapshot(
                        datasource_id=datasource_id,
                        metric_type="db_status",
                        data=snapshot_data,
                        collected_at=now(),  # 使用本地时间
                    )
                    db.add(snapshot)
                    await db.commit()

                # Handle connection failure - create alert and trigger diagnosis
                if connection_failed:
                    await _handle_connection_failure(db, datasource_id, datasource, status.get("error", "Unknown error"))

                # Route alert engine after metrics are persisted
                if not connection_failed:
                    await _route_alert_engine(db, datasource, snapshot_data)

                # Push to WebSocket subscribers
                await _push_to_subscribers(datasource_id, {
                    "type": "db_status",
                    "datasource_id": datasource_id,
                    "data": snapshot_data,
                    "collected_at": now().isoformat(),
                })
    except Exception as e:
        logger.error(f"Error collecting metrics for datasource {datasource_id}: {e}")
    finally:
        if connector is not None:
            try:
                await connector.close()
            except Exception:
                logger.debug("Failed to close connector for datasource %s", datasource_id, exc_info=True)


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
        normalized_threshold_rules: Dict[str, Any] = {}
        if isinstance(threshold_rules, dict):
            normalized_threshold_rules = threshold_rules
        elif isinstance(threshold_rules, list):
            for rule in threshold_rules:
                if not isinstance(rule, dict):
                    continue
                metric_name = rule.get("metric_name") or rule.get("name")
                if metric_name:
                    normalized_threshold_rules[metric_name] = rule

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
            current_value = extract_metric_value(metrics, alert.metric_name)
            if current_value is None:
                continue

            # Find the threshold rule for this metric
            # threshold_rules is a dict like {"cpu_usage": {"threshold": 80, "duration": 60}}
            threshold_rule = normalized_threshold_rules.get(alert.metric_name)

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


async def _auto_resolve_recovered_baseline_alerts(
    db,
    datasource_id: int,
    metrics: Dict[str, Any],
    collected_at: datetime,
    baseline_config: Dict[str, Any],
    current_violations: List[Dict[str, Any]],
):
    try:
        if not baseline_config.get("enabled"):
            return

        metric_names = [
            metric_name
            for metric_name, metric_config in baseline_config["metrics"].items()
            if metric_config.get("enabled")
        ]
        profiles = await get_profiles_for_slot(
            db,
            datasource_id=datasource_id,
            collected_at=collected_at,
            metric_names=metric_names,
        )

        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.datasource_id == datasource_id,
                    AlertMessage.alert_type == "baseline_deviation",
                    AlertMessage.status.in_(["active", "acknowledged"]),
                )
            )
        )
        active_alerts = result.scalars().all()
        if not active_alerts:
            return

        violating_metrics = {item["metric_name"] for item in current_violations}
        from backend.services.alert_service import AlertService

        for alert in active_alerts:
            if not alert.metric_name or alert.metric_name in violating_metrics:
                continue

            current_value = _threshold_checker._extract_metric_value(metrics, alert.metric_name)
            if current_value is None:
                continue

            profile = profiles.get(alert.metric_name)
            if not profile:
                continue

            upper_bound = compute_upper_bound(profile, baseline_config)
            if upper_bound is None:
                continue

            recovery_threshold = min(float(upper_bound), float(profile.p95_value or upper_bound))
            if float(current_value) <= recovery_threshold:
                await AlertService.resolve_alert(db, alert.id, resolved_value=float(current_value))
                logger.info(
                    "Auto-resolved baseline alert %s: %s recovered (current=%s <= %s)",
                    alert.id,
                    alert.metric_name,
                    current_value,
                    recovery_threshold,
                )
    except Exception as e:
        logger.error(f"Error auto-resolving baseline alerts for datasource {datasource_id}: {e}", exc_info=True)


async def _check_thresholds_and_trigger(db, datasource_id: int, metrics: Dict[str, Any]):
    """Check if metrics violate thresholds and trigger inspection if needed"""
    global _inspection_service, _threshold_checker, _baseline_detector

    if not _inspection_service:
        return

    try:
        # 检查数据源是否在静默期内
        result = await db.execute(
            select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
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

        if not config:
            return

        effective_config = await resolve_effective_inspection_config(db, config)
        threshold_rules = getattr(effective_config, "threshold_rules", None) or {}
        baseline_config = normalize_baseline_config(getattr(effective_config, "baseline_config", None))
        if not threshold_rules and not baseline_config.get("enabled"):
            return

        collected_at = now()
        baseline_profiles = {}
        if baseline_config.get("enabled"):
            baseline_profiles = await refresh_current_slot_profiles(
                db,
                datasource_id=datasource_id,
                collected_at=collected_at,
                baseline_config=baseline_config,
            )

        # Check thresholds
        violations = _threshold_checker.check_thresholds(
            datasource_id=datasource_id,
            metrics=metrics,
            threshold_rules=threshold_rules
        )
        baseline_violations = _baseline_detector.check_baselines(
            datasource_id=datasource_id,
            metrics=metrics,
            profiles_by_metric=baseline_profiles,
            baseline_config=baseline_config,
        )

        # Auto-resolve alerts for metrics that have recovered
        await _auto_resolve_recovered_alerts(db, datasource_id, metrics, threshold_rules, violations)
        await _auto_resolve_recovered_baseline_alerts(
            db,
            datasource_id=datasource_id,
            metrics=metrics,
            collected_at=collected_at,
            baseline_config=baseline_config,
            current_violations=baseline_violations,
        )

        # Trigger inspection and create alert for each violation
        for violation in violations:
            metric_name = violation['metric_name']
            reason = (
                f"{metric_name}={violation['current_value']:.2f} > "
                f"{violation['threshold']} for {violation['violation_duration']:.0f}s"
            )

            # Skip duplicate alerts only when the same metric still has an active issue
            active_alert_result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.datasource_id == datasource_id,
                        AlertMessage.alert_type == "threshold_violation",
                        AlertMessage.metric_name == metric_name,
                        AlertMessage.status.in_(["active", "acknowledged"])
                    )
                ).limit(1)
            )
            active_alert = active_alert_result.scalar_one_or_none()

            if active_alert:
                logger.debug(
                    f"Skipping duplicate anomaly trigger for datasource {datasource_id} metric {metric_name} - "
                    f"active alert {active_alert.id} exists"
                )
                continue

            logger.info(f"Triggering anomaly inspection for datasource {datasource_id}: {reason}")

            # Create metric snapshot for the trigger
            metric_snapshot = {
                "violation": violation,
                "full_metrics": metrics,
                "timestamp": now().isoformat()
            }

            # Create alert for the violation
            from backend.services.alert_service import AlertService

            # Calculate severity based on percentage over threshold
            percent_over = ((violation['current_value'] - violation['threshold']) / violation['threshold']) * 100
            severity = AlertService.calculate_severity(percent_over)

            alert = await AlertService.create_alert(
                db=db,
                datasource_id=datasource_id,
                alert_type="threshold_violation",
                severity=severity,
                metric_name=violation['metric_name'],
                metric_value=violation['current_value'],
                threshold_value=violation['threshold'],
                trigger_reason=reason
            )

            # Trigger inspection asynchronously
            await _inspection_service.trigger_inspection(
                db=db,
                datasource_id=datasource_id,
                trigger_type="anomaly",
                reason=reason,
                metric_snapshot=metric_snapshot,
                alert_id=alert.id
            )

        for violation in baseline_violations:
            metric_name = violation["metric_name"]
            reason = (
                f"{metric_name}={violation['current_value']:.2f} 高于该实例基线窗口上界 "
                f"{violation['upper_bound']:.2f}（P95={violation['baseline_p95']}, "
                f"样本={violation['sample_count']}，时间槽={violation['slot_label']}）"
            )

            active_alert_result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.datasource_id == datasource_id,
                        AlertMessage.alert_type == "baseline_deviation",
                        AlertMessage.metric_name == metric_name,
                        AlertMessage.status.in_(["active", "acknowledged"]),
                    )
                ).limit(1)
            )
            active_alert = active_alert_result.scalar_one_or_none()
            if active_alert:
                logger.debug(
                    "Skipping duplicate baseline trigger for datasource %s metric %s - active alert %s exists",
                    datasource_id,
                    metric_name,
                    active_alert.id,
                )
                continue

            from backend.services.alert_service import AlertService

            alert = await AlertService.create_alert(
                db=db,
                datasource_id=datasource_id,
                alert_type="baseline_deviation",
                severity=violation.get("severity") or "medium",
                metric_name=metric_name,
                metric_value=violation["current_value"],
                threshold_value=violation["upper_bound"],
                trigger_reason=reason,
            )

            metric_snapshot = {
                "baseline_violation": violation,
                "full_metrics": metrics,
                "timestamp": collected_at.isoformat(),
            }
            await _inspection_service.trigger_inspection(
                db=db,
                datasource_id=datasource_id,
                trigger_type="baseline",
                reason=reason,
                metric_snapshot=metric_snapshot,
                alert_id=alert.id,
            )

    except Exception as e:
        logger.error(f"Error checking thresholds for datasource {datasource_id}: {e}", exc_info=True)


async def _get_enabled_inspection_config(db, datasource_id: int):
    from backend.models.inspection_config import InspectionConfig

    result = await db.execute(
        select(InspectionConfig).where(
            InspectionConfig.datasource_id == datasource_id,
            InspectionConfig.enabled == True,
        )
    )
    return result.scalar_one_or_none()


async def _route_alert_engine(db, datasource, metrics: Dict[str, Any]):
    try:
        config = await _get_enabled_inspection_config(db, datasource.id)
        if not config:
            return

        from backend.services.alert_ai_service import resolve_effective_alert_engine_mode

        effective_config = await resolve_effective_inspection_config(db, config)
        effective_mode = await resolve_effective_alert_engine_mode(db, effective_config)
        if effective_mode == "ai":
            await _check_ai_alerts_and_trigger(db, datasource, effective_config, metrics, mode="formal")
            return

        await _check_thresholds_and_trigger(db, datasource.id, metrics)

        if getattr(effective_config, "ai_shadow_enabled", False):
            await _check_ai_alerts_and_trigger(db, datasource, effective_config, metrics, mode="shadow")
    except Exception as e:
        logger.error(
            "Error routing alert engine for datasource %s: %s",
            getattr(datasource, "id", "unknown"),
            e,
            exc_info=True,
        )


async def _check_ai_alerts_and_trigger(db, datasource, config, metrics: Dict[str, Any], mode: str = "formal"):
    try:
        from backend.services.alert_ai_service import (
            _merge_gate_skip_reason,
            apply_alert_ai_result,
            build_alert_ai_feature_summary,
            decide_alert_ai_candidate,
            evaluate_alert_ai_policy,
            get_or_create_runtime_state,
            normalize_analysis_config,
            resolve_configured_alert_ai_policy_binding,
            should_skip_candidate_due_to_interval,
            _resolve_current_alert_severity,
        )
        from backend.services.monitoring_scheduler_service import get_monitoring_collection_interval_seconds

        binding = await resolve_configured_alert_ai_policy_binding(db, config)
        if not binding:
            return

        runtime_state = await get_or_create_runtime_state(db, datasource.id, binding)
        collected_at = now()
        sampling_interval_seconds = await get_monitoring_collection_interval_seconds(db)
        snapshots_result = await db.execute(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.datasource_id == datasource.id,
                MetricSnapshot.metric_type == "db_status",
                MetricSnapshot.collected_at >= collected_at - timedelta(hours=24),
            )
            .order_by(desc(MetricSnapshot.collected_at))
            .limit(1440)
        )
        snapshots_desc = snapshots_result.scalars().all()
        current_alert_severity = await _resolve_current_alert_severity(db, datasource.id, runtime_state, binding)
        gate_decision, _metric_features = decide_alert_ai_candidate(
            binding=binding,
            state=runtime_state,
            current_metrics=metrics,
            collected_at=collected_at,
            snapshots_desc=snapshots_desc,
            threshold_rules=getattr(config, "threshold_rules", None),
            current_alert_severity=current_alert_severity,
            datasource=datasource,
            sampling_interval_seconds=sampling_interval_seconds,
        )

        if mode == "formal":
            runtime_state.samples_seen = int(runtime_state.samples_seen or 0) + 1
            runtime_state.last_gate_reason = gate_decision.gate_reason
            runtime_state.last_gate_metrics = gate_decision.gate_metrics

        if not gate_decision.should_evaluate:
            if mode == "formal":
                runtime_state.gate_skips_by_reason = _merge_gate_skip_reason(
                    runtime_state.gate_skips_by_reason,
                    gate_decision.gate_reason,
                )
            await db.commit()
            return

        if mode == "formal":
            runtime_state.candidate_hits = int(runtime_state.candidate_hits or 0) + 1

        analysis_config = normalize_analysis_config(binding.analysis_config)
        should_skip, skip_reason = should_skip_candidate_due_to_interval(
            runtime_state,
            gate_decision,
            analysis_config,
            collected_at,
        )
        if should_skip:
            if mode == "formal":
                runtime_state.gate_skips_by_reason = _merge_gate_skip_reason(
                    runtime_state.gate_skips_by_reason,
                    skip_reason,
                )
            await db.commit()
            return

        feature_summary = await build_alert_ai_feature_summary(
            db,
            datasource,
            binding.rule_text,
            metrics,
            collected_at,
            compiled_trigger_profile=binding.compiled_trigger_profile,
            runtime_state=runtime_state,
            gate_decision=gate_decision,
            snapshots_desc=snapshots_desc,
            sampling_interval_seconds=sampling_interval_seconds,
        )
        judge_result, evaluation_log = await evaluate_alert_ai_policy(
            db,
            datasource,
            binding,
            feature_summary,
            runtime_state,
            mode=mode,
        )
        if mode == "formal":
            runtime_state.ai_evaluations = int(runtime_state.ai_evaluations or 0) + 1
            runtime_state.last_ai_evaluated_at = collected_at
            runtime_state.last_candidate_type = gate_decision.candidate_type
            runtime_state.last_candidate_fingerprint = gate_decision.fingerprint
            runtime_state.last_gate_reason = gate_decision.gate_reason
            runtime_state.last_gate_metrics = gate_decision.gate_metrics
        result = await apply_alert_ai_result(
            db,
            datasource,
            binding,
            runtime_state,
            judge_result,
            inspection_service=_inspection_service,
            evaluation_log=evaluation_log,
            mode=mode,
        )
        await db.commit()
        logger.debug(
            "AI alert evaluation finished for datasource %s mode=%s decision=%s action=%s",
            datasource.id,
            mode,
            judge_result.decision,
            result.get("action"),
        )
    except Exception as e:
        logger.error(
            "Error checking AI alerts for datasource %s: %s",
            getattr(datasource, "id", "unknown"),
            e,
            exc_info=True,
        )


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

        # Skip duplicate alerts only when the connection failure is still active
        active_alert_result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.datasource_id == datasource_id,
                    AlertMessage.alert_type == "system_error",
                    AlertMessage.metric_name == "connection_status",
                    AlertMessage.status.in_(["active", "acknowledged"])
                )
            ).limit(1)
        )
        active_alert = active_alert_result.scalar_one_or_none()

        if active_alert:
            logger.debug(
                f"Skipping duplicate connection_failure trigger for datasource {datasource_id} - "
                f"active alert {active_alert.id} exists"
            )
            return

        error_detail = (error_message or "").strip(" ：:")
        trigger_reason = f"数据库连接失败：{error_detail}" if error_detail else "数据库连接失败"

        # Create critical alert for connection failure
        alert = await AlertService.create_alert(
            db=db,
            datasource_id=datasource_id,
            alert_type="system_error",
            severity="critical",
            metric_name="connection_status",
            metric_value=0.0,  # 0 = failed
            threshold_value=1.0,  # 1 = expected success
            trigger_reason=trigger_reason
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
                metric_snapshot=metric_snapshot,
                alert_id=alert.id
            )

            logger.info(f"Triggered AI diagnosis for connection failure: datasource {datasource_id}")

    except Exception as e:
        logger.error(f"Error handling connection failure for datasource {datasource_id}: {e}", exc_info=True)


async def _handle_network_probe_failure(host: str):
    """创建全局网络探针失败告警（若尚无活跃告警）"""
    try:
        from backend.services.alert_service import AlertService
        async with async_session() as db:
            # 检查是否已存在活跃的网络告警，避免重复
            result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.metric_name == "network_probe",
                        AlertMessage.status.in_(["active", "acknowledged"])
                    )
                )
            )
            if result.scalars().first():
                logger.debug("Network probe alert already active, skipping creation")
                return

            await AlertService.create_alert(
                db=db,
                datasource_id=0,
                alert_type="system_error",
                severity="critical",
                metric_name="network_probe",
                trigger_reason=f"网络探针失败：无法连通 {host}"
            )
            logger.warning(f"Created network probe failure alert (host={host})")
    except Exception as e:
        logger.error(f"Error creating network probe alert: {e}", exc_info=True)


async def _auto_resolve_network_probe_alerts():
    """探针恢复后自动解除所有活跃的网络告警"""
    try:
        from backend.services.alert_service import AlertService
        async with async_session() as db:
            result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.metric_name == "network_probe",
                        AlertMessage.status.in_(["active", "acknowledged"])
                    )
                )
            )
            alerts = result.scalars().all()
            for alert in alerts:
                await AlertService.resolve_alert(db, alert.id)
                logger.info(f"Auto-resolved network probe alert {alert.id}: network restored")
    except Exception as e:
        logger.error(f"Error auto-resolving network probe alerts: {e}", exc_info=True)


async def collect_all_metrics():
    """Collect metrics for all active datasources."""
    try:
        # 网络探针：采集前先检测网络连通性
        from backend.services.network_probe import check_network
        from backend.services.config_service import get_config as _get_config

        async with async_session() as _probe_db:
            probe_host = await _get_config(_probe_db, "network_probe_host", default="127.0.0.1")

        network_ok = await check_network(probe_host)
        if not network_ok:
            logger.warning(f"Network probe failed (host={probe_host}), skipping all datasource collection")
            await _handle_network_probe_failure(probe_host)
            return

        # 网络正常，自动解除已有的网络告警
        await _auto_resolve_network_probe_alerts()

        async with async_session() as db:
            result = await db.execute(
                select(Datasource.id).where(Datasource.is_active == True)
            )
            datasource_ids = [row[0] for row in result.fetchall()]

        tasks = [collect_metrics_for_connection(ds_id) for ds_id in datasource_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error in collect_all_metrics: {e}", exc_info=True)


def start_scheduler(interval_seconds: int = 60):
    """Start the APScheduler for periodic metric collection."""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()

    scheduler.add_job(
        collect_all_metrics,
        "interval",
        seconds=interval_seconds,
        id="metric_collector",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
        logger.info(f"Metric collector started (interval: {interval_seconds}s)")
        return

    logger.info(f"Metric collector refreshed (interval: {interval_seconds}s)")


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
