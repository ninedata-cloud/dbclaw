"""
Notification dispatcher background task
Processes pending alerts and sends notifications based on subscriptions
"""

import asyncio
import logging
import re
from datetime import timedelta
from typing import List
from sqlalchemy import select

from backend.database import async_session
from backend.services.alert_service import (
    AlertService,
    extract_connection_failure_detail,
    is_connection_status_alert,
)
from backend.services.notification_service import NotificationService
from backend.services.aggregation_engine import AggregationEngine
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.utils.datetime_helper import now, format_local_datetime

logger = logging.getLogger(__name__)

AI_ALERT_METRIC_LABELS = {
    "cpu_usage": "CPU 使用率",
    "memory_usage": "内存使用率",
    "disk_usage": "磁盘使用率",
    "connections_active": "活跃连接数",
    "connections_total": "总连接数",
    "connections_waiting": "等待连接数",
    "qps": "QPS",
    "tps": "TPS",
    "iops": "IOPS",
    "throughput": "吞吐量",
    "cache_hit_rate": "缓存命中率",
    "lock_waiting": "锁等待数",
    "longest_transaction_sec": "最长事务时长",
}

AI_ALERT_METRIC_ALIASES = {
    "cpu_usage": ["cpu_usage", "cpu_usage_percent", "cpu_percent"],
    "memory_usage": ["memory_usage", "memory_usage_percent", "mem_percent"],
    "disk_usage": ["disk_usage", "disk_usage_percent", "disk_percent"],
    "connections_active": ["connections_active", "threads_running", "active_connections", "connection_count"],
    "connections_total": ["connections_total", "threads_connected", "total_connections"],
    "connections_waiting": ["connections_waiting", "lock_waiting_connections", "waiting_connections"],
    "qps": ["qps", "questions_per_second"],
    "tps": ["tps", "transactions_per_second"],
    "iops": ["iops"],
    "throughput": ["throughput"],
    "cache_hit_rate": ["cache_hit_rate", "buffer_pool_hit_rate"],
    "lock_waiting": ["lock_waiting", "lock_waits"],
    "longest_transaction_sec": ["longest_transaction_sec"],
}

AI_ALERT_PERCENT_METRICS = {"cpu_usage", "memory_usage", "disk_usage", "cache_hit_rate"}
AI_ALERT_INTEGER_METRICS = {"connections_active", "connections_total", "connections_waiting", "lock_waiting"}
NETWORK_PROBE_METRIC_NAME = "network_probe"
MAX_ALERT_HISTORY_DAYS = 3


def _get_required_integration_params(integration) -> list[str]:
    """从 Integration config_schema 提取必填参数"""
    schema = integration.config_schema or {}
    required = schema.get("required") or []
    return [key for key in required if isinstance(key, str) and key.strip()]


def _alert_type_display(alert_type: str | None) -> str:
    return {
        "threshold_violation": "超过阈值",
        "baseline_deviation": "偏离基线",
        "custom_expression": "自定义表达式",
        "system_error": "系统错误",
        "ai_policy_violation": "AI 判警",
    }.get(alert_type or "", alert_type or "未知")


def _severity_display(severity: str | None) -> str:
    return {
        "critical": "严重",
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(severity or "", severity or "未知")


def _coerce_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.endswith("%"):
            stripped = stripped[:-1]
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _lookup_metric_value(raw_metrics: dict[str, object] | None, metric_name: str) -> float | None:
    if not isinstance(raw_metrics, dict):
        return None
    for alias in AI_ALERT_METRIC_ALIASES.get(metric_name, [metric_name]):
        value = _coerce_float(raw_metrics.get(alias))
        if value is not None:
            return value
    return None


def _format_native_metric_value(metric_name: str, value: float) -> str:
    if metric_name in AI_ALERT_PERCENT_METRICS:
        return f"{value:.1f}%"
    if metric_name in AI_ALERT_INTEGER_METRICS:
        return str(int(round(value)))
    if metric_name == "longest_transaction_sec":
        return f"{value:.0f} 秒"
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:.2f}"


def _render_notification_metric_summary(raw_metrics: dict[str, object] | None, focus_metrics: list[str] | None) -> str | None:
    metric_keys = [metric for metric in (focus_metrics or []) if metric]
    if not metric_keys and isinstance(raw_metrics, dict):
        metric_keys = [key for key in AI_ALERT_METRIC_LABELS if _lookup_metric_value(raw_metrics, key) is not None]

    lines: list[str] = []
    seen: set[str] = set()
    for metric_name in metric_keys:
        if metric_name in seen:
            continue
        seen.add(metric_name)
        value = _lookup_metric_value(raw_metrics, metric_name)
        if value is None:
            continue
        label = AI_ALERT_METRIC_LABELS.get(metric_name, metric_name)
        lines.append(f"- {label}：{_format_native_metric_value(metric_name, value)}")
        if len(lines) >= 6:
            break
    return "\n".join(lines) if lines else None


def _format_diagnosis_markdown(text: str | None, *, max_items: int = 5) -> str | None:
    content = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        return None

    raw_items: list[str] = []
    if "\n" in content:
        raw_items = [line.strip() for line in content.split("\n")]
    else:
        raw_items = re.split(r"[；;]\s*", content)

    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        normalized = re.sub(r"^[\-\*\u2022]+\s*", "", raw).strip()
        normalized = re.sub(r"^\d+[\.\)、]\s*", "", normalized).strip()
        normalized = normalized.strip("：:；; ")
        if not normalized:
            continue
        dedup_key = normalized.lower()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        items.append(normalized)
        if len(items) >= max_items:
            break

    if not items:
        return None
    if len(items) == 1:
        return items[0][:500]
    return "\n".join(f"- {item[:220]}" for item in items)


async def _build_ai_native_metric_summary(db, alert) -> str | None:
    if getattr(alert, "alert_type", None) != "ai_policy_violation" or not getattr(alert, "datasource_id", None):
        return None

    from backend.models.alert_ai_evaluation_log import AlertAIEvaluationLog
    from backend.models.datasource_metric import DatasourceMetric

    evaluation_result = await db.execute(
        select(AlertAIEvaluationLog)
        .where(
            AlertAIEvaluationLog.datasource_id == alert.datasource_id,
            AlertAIEvaluationLog.is_accepted == True,
            AlertAIEvaluationLog.decision == "alert",
        )
        .order_by(AlertAIEvaluationLog.created_at.desc(), AlertAIEvaluationLog.id.desc())
        .limit(1)
    )
    evaluation_log = evaluation_result.scalar_one_or_none()

    focus_metrics: list[str] = []
    metric_features = {}
    if evaluation_log and isinstance(evaluation_log.feature_summary, dict):
        focus_metrics = [metric for metric in (evaluation_log.feature_summary.get("focus_metrics") or []) if isinstance(metric, str)]
        metric_features = evaluation_log.feature_summary.get("metric_features") or {}
        if isinstance(metric_features, dict):
            feature_lines = _render_notification_metric_summary(
                {metric: feature.get("current") for metric, feature in metric_features.items() if isinstance(feature, dict)},
                focus_metrics or list(metric_features.keys()),
            )
            if feature_lines:
                return feature_lines

    snapshot_result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == alert.datasource_id,
            DatasourceMetric.metric_type == "db_status",
        )
        .order_by(DatasourceMetric.collected_at.desc(), DatasourceMetric.id.desc())
        .limit(1)
    )
    latest_snapshot = snapshot_result.scalar_one_or_none()
    if latest_snapshot and isinstance(latest_snapshot.data, dict):
        return _render_notification_metric_summary(
            latest_snapshot.data,
            focus_metrics,
        )

    return None


def _is_connection_failure_alert(alert) -> bool:
    return is_connection_status_alert(getattr(alert, "alert_type", None), getattr(alert, "metric_name", None))


def _build_active_alert_payload(
    alert,
    datasource,
    diagnosis_payload: dict[str, str | None],
    alert_url: str | None,
    report_url: str | None,
    native_metric_summary: str | None = None,
) -> dict:
    datasource_name = datasource.name if datasource else "未知数据源"
    timestamp = format_local_datetime(alert.created_at) if alert.created_at else format_local_datetime(now())

    payload = {
        "title": f"【{alert.severity.upper()}】{datasource_name} 告警",
        "content": alert.content,
        "severity": alert.severity,
        "datasource_name": datasource_name,
        "alert_id": alert.id,
        "alert_url": alert_url,
        "report_url": report_url,
        "timestamp": timestamp,
        "created_at": timestamp if alert.created_at else None,
        "resolved_at": None,
        "ai_diagnosis_summary": diagnosis_payload.get("summary"),
        "root_cause": diagnosis_payload.get("root_cause"),
        "recommended_actions": diagnosis_payload.get("recommended_actions"),
        "diagnosis_status": diagnosis_payload.get("status"),
        "status": "active",
        "alert_type": alert.alert_type,
        "metric_name": alert.metric_name,
        "metric_value": alert.metric_value,
        "resolved_value": None,
        "threshold_value": alert.threshold_value,
        "trigger_reason": alert.trigger_reason,
        "native_metric_summary": native_metric_summary,
        "root_cause_markdown": _format_diagnosis_markdown(diagnosis_payload.get("root_cause")),
        "recommended_actions_markdown": _format_diagnosis_markdown(diagnosis_payload.get("recommended_actions")),
        "ai_diagnosis_summary_markdown": _format_diagnosis_markdown(diagnosis_payload.get("summary"), max_items=3),
    }

    if _is_connection_failure_alert(alert):
        detail = extract_connection_failure_detail(alert.trigger_reason)
        content_lines = ["状态：数据库连接失败"]
        if detail:
            content_lines.append(f"错误详情：{detail}")
        payload.update({
            "title": f"【{alert.severity.upper()}】{datasource_name} 数据库连接失败",
            "content": "\n".join(content_lines),
            "alert_type": "连接失败",
            "metric_name": None,
            "metric_value": None,
            "threshold_value": None,
            "trigger_reason": detail or "数据库连接失败",
        })

    return payload


def _build_recovery_alert_payload(alert, datasource, diagnosis_summary: str | None = None) -> dict:
    datasource_name = datasource.name if datasource else "未知数据源"
    created_at_str = format_local_datetime(alert.created_at) if alert.created_at else None
    resolved_at_str = format_local_datetime(alert.resolved_at) if alert.resolved_at else format_local_datetime(now())
    diagnosis_summary_line = f"AI 总结：{diagnosis_summary}\n" if diagnosis_summary else ""

    recovery_metric_line = ""
    recovery_value = None
    if alert.metric_name and alert.resolved_value is not None:
        recovery_value = alert.resolved_value
        recovery_metric_line = f"\n恢复后值：{alert.metric_name} = {alert.resolved_value:.2f}"
    elif alert.metric_name and alert.metric_value is not None:
        recovery_value = alert.metric_value
        recovery_metric_line = f"\n恢复后值：{alert.metric_name} = {alert.metric_value:.2f}"

    payload = {
        "title": f"【已恢复】{datasource_name} 告警已恢复",
        "content": (
            f"告警类型：{_alert_type_display(alert.alert_type)}\n"
            f"严重程度：{_severity_display(alert.severity)}\n\n"
            f"{alert.content}{recovery_metric_line}\n\n"
            f"{diagnosis_summary_line}"
            f"告警时间：{created_at_str or '未知'}\n"
            f"恢复时间：{resolved_at_str}"
        ),
        "severity": alert.severity,
        "alert_type": alert.alert_type,
        "datasource_name": datasource_name,
        "alert_id": alert.id,
        "timestamp": resolved_at_str,
        "created_at": created_at_str,
        "resolved_at": resolved_at_str,
        "status": "resolved",
        "metric_name": alert.metric_name,
        "metric_value": alert.metric_value,
        "resolved_value": alert.resolved_value,
        "recovery_value": recovery_value,
        "threshold_value": alert.threshold_value,
        "trigger_reason": alert.trigger_reason,
    }

    if _is_connection_failure_alert(alert):
        detail = extract_connection_failure_detail(alert.trigger_reason)
        content_lines = ["状态：数据库连接已恢复"]
        if detail:
            content_lines.append(f"上一条错误：{detail}")
        content_lines.append(f"告警时间：{created_at_str or '未知'}")
        content_lines.append(f"恢复时间：{resolved_at_str}")
        payload.update({
            "title": f"【已恢复】{datasource_name} 数据库连接已恢复",
            "content": "\n".join(content_lines),
            "alert_type": "连接恢复",
            "metric_name": None,
            "metric_value": None,
            "resolved_value": None,
            "recovery_value": None,
            "threshold_value": None,
            "trigger_reason": detail or "数据库连接已恢复",
        })

    return payload


async def start_notification_dispatcher():
    """
    Background task that processes pending alerts and sends notifications.
    Runs every 30 seconds.
    """
    logger.info("Notification dispatcher started")

    while True:
        try:
            await _process_pending_alerts()
        except Exception as e:
            logger.error(f"Notification dispatcher error: {e}", exc_info=True)

        # Wait 30 seconds before next cycle
        await asyncio.sleep(30)


async def _process_pending_alerts():
    """Process all pending alerts and send notifications"""
    async with async_session() as db:
        cooldown_minutes = await AggregationEngine._get_notification_cooldown_minutes(db)
        # Get active alerts that are due for notification (based on cooldown window)
        alerts = await AlertService.get_pending_notifications(db, minutes=cooldown_minutes)

        if alerts:
            logger.debug(f"Processing {len(alerts)} pending alerts")
            has_probe_failure = await _has_active_network_probe_failure(db)

            # Get all active subscriptions
            subscriptions = await AlertService.get_all_subscriptions(db)

            if not subscriptions:
                logger.debug("No active subscriptions found")
            else:
                # Process each alert
                for alert in alerts:
                    if _is_historical_alert(alert):
                        logger.info(
                            "Skipping alert %s: historical alert older than %s days",
                            alert.id,
                            MAX_ALERT_HISTORY_DAYS,
                        )
                        continue

                    if _should_skip_for_probe_failure(alert, has_probe_failure):
                        logger.info(
                            "Skipping alert %s: active network probe failure, only %s alert can be sent",
                            alert.id,
                            NETWORK_PROBE_METRIC_NAME,
                        )
                        continue

                    # Check if datasource is in silence period
                    if await _is_datasource_silenced(db, alert.datasource_id):
                        logger.debug(f"Skipping alert {alert.id}: datasource {alert.datasource_id} is silenced")
                        continue

                    # Check if datasource exists (may have been deleted)
                    from backend.models.datasource import Datasource
                    from sqlalchemy import select
                    ds_result = await db.execute(
                        select(Datasource).where(Datasource.id == alert.datasource_id, alive_filter(Datasource))
                    )
                    datasource = ds_result.scalar_one_or_none()

                    # Pre-diagnosis: run sync diagnosis before sending notifications (max 60s timeout)
                    diagnosis_result = {
                        "root_cause": None,
                        "recommended_actions": None,
                        "summary": None,
                        "status": None,
                    }
                    if alert.event_id and datasource:
                        try:
                            from backend.models.alert_event import AlertEvent
                            from backend.services.alert_service import (
                                get_event_ai_config_for_datasource,
                                run_sync_diagnosis,
                                should_refresh_event_diagnosis,
                            )

                            event_result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert.event_id))
                            event_obj = event_result.scalar_one_or_none()
                            event_ai_config = await get_event_ai_config_for_datasource(db, alert.datasource_id)
                            if event_obj and should_refresh_event_diagnosis(event_obj, event_ai_config):
                                diagnosis_result = await run_sync_diagnosis(db, alert.event_id, timeout_seconds=600)
                            elif event_obj:
                                diagnosis_result = {
                                    "root_cause": event_obj.root_cause,
                                    "recommended_actions": event_obj.recommended_actions,
                                    "summary": event_obj.ai_diagnosis_summary,
                                    "status": event_obj.diagnosis_status,
                                }
                        except Exception as diag_err:
                            logger.warning(f"Pre-diagnosis failed for alert {alert.id}: {diag_err}")
                    elif alert.event_id and not datasource:
                        logger.debug(f"Skipping diagnosis for alert {alert.id}: datasource {alert.datasource_id} not found")

                    for subscription in subscriptions:
                        try:
                            # Check if subscription matches alert (datasource, severity, time range)
                            if not await NotificationService.check_subscription_match(alert, subscription):
                                continue

                            # Check aggregation rules
                            aggregation_engine = AggregationEngine()
                            if not await aggregation_engine.should_send_alert(db, alert, subscription):
                                logger.debug(
                                    f"Alert {alert.id} suppressed by aggregation rules "
                                    f"for subscription {subscription.id}"
                                )
                                continue

                            # Send notifications via Integration system
                            if not subscription.integration_targets:
                                logger.warning(
                                    f"Subscription {subscription.id} has no targets configured, skipping"
                                )
                                continue

                            # Pre-send dedup: check if already delivered for this alert+subscription
                            if await _already_delivered(
                                db,
                                alert.id,
                                subscription.id,
                                cooldown_minutes=cooldown_minutes,
                            ):
                                logger.debug(
                                    f"Skipping alert {alert.id} for subscription {subscription.id}: already delivered"
                                )
                                continue

                            delivery_logs = await _send_via_integration(
                                db, alert, subscription, diagnosis_result
                            )

                            # Mark alert as notified after first successful send
                            if delivery_logs and any(l.status == "sent" for l in delivery_logs):
                                await _mark_alert_notified(db, alert)
                                # Trigger async background diagnosis for deeper analysis (UI side)
                                if alert.event_id:
                                    from backend.models.alert_event import AlertEvent
                                    from backend.services.alert_service import (
                                        get_event_ai_config_for_datasource,
                                        should_refresh_event_diagnosis,
                                    )

                                    event_result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert.event_id))
                                    event_obj = event_result.scalar_one_or_none()
                                    event_ai_config = await get_event_ai_config_for_datasource(db, alert.datasource_id)
                                    if event_obj and should_refresh_event_diagnosis(event_obj, event_ai_config):
                                        asyncio.create_task(_trigger_alert_auto_diagnosis(alert.event_id))

                            logger.info(
                                f"Sent {len(delivery_logs)} notifications for alert {alert.id} "
                                f"(subscription {subscription.id})"
                            )

                        except Exception as e:
                            logger.error(
                                f"Error processing alert {alert.id} for subscription {subscription.id}: {e}",
                                exc_info=True
                            )

        # Process recovery notifications for recently resolved alerts
        await _process_recovery_notifications(db)




async def _already_delivered(
    db,
    alert_id: int,
    subscription_id: int,
    cooldown_minutes: int = 0,
) -> bool:
    """Check if this alert+subscription was delivered within cooldown window."""
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from sqlalchemy import select, and_

    filters = [
        AlertDeliveryLog.alert_id == alert_id,
        AlertDeliveryLog.subscription_id == subscription_id,
        AlertDeliveryLog.status == "sent",
    ]
    if cooldown_minutes > 0:
        cutoff_time = now() - timedelta(minutes=cooldown_minutes)
        filters.append(AlertDeliveryLog.sent_at >= cutoff_time)

    result = await db.execute(
        select(AlertDeliveryLog.id).where(
            and_(*filters)
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _trigger_alert_auto_diagnosis(alert_event_id: int):
    """Trigger AI auto-diagnosis for an alert event, non-blocking."""
    try:
        from backend.services.alert_service import AlertService
        async with async_session() as db:
            await AlertService.trigger_auto_diagnosis(db, alert_event_id)
    except Exception as e:
        logger.error(f"Failed to trigger auto-diagnosis for alert event {alert_event_id}: {e}", exc_info=True)


async def _mark_alert_notified(db, alert):
    """Mark alert as notified so it won't be picked up again"""
    from datetime import datetime
    alert.notified_at = now()
    await db.commit()


async def _send_via_integration(db, alert, subscription, diagnosis_result=None):
    """通过 Integration 系统发送通知"""
    from backend.config import get_settings
    from backend.models.integration import Integration, IntegrationExecutionLog
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from backend.models.datasource import Datasource
    from backend.services.integration_executor import IntegrationExecutor
    from backend.services.public_share_service import PublicShareService
    from backend.services.alert_service import normalize_alert_diagnosis_fields
    from sqlalchemy import select
    from datetime import datetime

    delivery_logs = []

    datasource = None
    if alert.datasource_id:
        ds_result = await db.execute(
            select(Datasource).where(Datasource.id == alert.datasource_id, alive_filter(Datasource))
        )
        datasource = ds_result.scalar_one_or_none()

    settings = get_settings()
    alert_url = None
    report_url = None
    base_url = await PublicShareService.get_external_base_url(db)
    if base_url:
        alert_token = PublicShareService.create_alert_share_token(alert.id, settings.public_share_expire_minutes)
        alert_url = f"{base_url}/api/alerts/public/{alert.id}/page?token={alert_token}"

        linked_report = await PublicShareService.get_report_by_alert_id(db, alert.id)
        if linked_report:
            report_token = PublicShareService.create_report_share_token(linked_report.id, settings.public_share_expire_minutes)
            report_url = f"{base_url}/api/inspections/report/public/{linked_report.id}/page?token={report_token}"

    for target in (subscription.integration_targets or []):
        if not isinstance(target, dict):
            continue
        if not target.get("enabled", True):
            continue
        if "alert" not in (target.get("notify_on") or ["alert"]):
            continue

        integration_id = target.get("integration_id")
        if not integration_id:
            continue

        integration = await get_alive_by_id(db, Integration, int(integration_id))
        if not integration or not integration.is_enabled:
            logger.warning(f"Integration {integration_id} 不存在或已禁用")
            continue

        # Fetch AI diagnosis fields from alert event (fallback if sync diagnosis didn't run)
        ai_diagnosis_summary = None
        root_cause = None
        recommended_actions = None
        diagnosis_status = None

        if diagnosis_result:
            ai_diagnosis_summary = diagnosis_result.get("summary")
            root_cause = diagnosis_result.get("root_cause")
            recommended_actions = diagnosis_result.get("recommended_actions")
            diagnosis_status = diagnosis_result.get("status")
        else:
            # Fallback: try to get from alert event if sync diagnosis wasn't run
            if alert.event_id:
                from backend.models.alert_event import AlertEvent
                event_result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert.event_id))
                event_obj = event_result.scalar_one_or_none()
                if event_obj:
                    ai_diagnosis_summary = event_obj.ai_diagnosis_summary
                    root_cause = event_obj.root_cause
                    recommended_actions = event_obj.recommended_actions
                    diagnosis_status = event_obj.diagnosis_status

        normalized_diagnosis = normalize_alert_diagnosis_fields(
            root_cause=root_cause,
            recommended_actions=recommended_actions,
            summary=ai_diagnosis_summary,
        )
        ai_diagnosis_summary = normalized_diagnosis["summary"]
        root_cause = normalized_diagnosis["root_cause"]
        recommended_actions = normalized_diagnosis["recommended_actions"]
        native_metric_summary = await _build_ai_native_metric_summary(db, alert)

        payload = _build_active_alert_payload(
            alert,
            datasource,
            {
                "summary": ai_diagnosis_summary,
                "root_cause": root_cause,
                "recommended_actions": recommended_actions,
                "status": diagnosis_status,
            },
            alert_url,
            report_url,
            native_metric_summary=native_metric_summary,
        )

        params = target.get("params") or {}
        target_id = target.get("target_id")
        target_name = target.get("name") or integration.name
        required_params = _get_required_integration_params(integration)
        missing_params = [key for key in required_params if not params.get(key)]
        executor = IntegrationExecutor(db, logger)
        start_time = now()

        if missing_params:
            missing_params_text = ", ".join(missing_params)
            error_message = f"Integration 缺少必填参数: {missing_params_text}"
            logger.warning(
                "跳过告警通知 target=%s integration=%s subscription=%s，原因：%s",
                target_name,
                integration.integration_id,
                subscription.id,
                error_message,
            )

            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type="subscription_target",
                target_ref=str(target_id) if target_id is not None else None,
                subscription_id=subscription.id,
                target_name=target_name,
                params_snapshot=params,
                payload_summary={"alert_id": alert.id, "severity": alert.severity},
                trigger_source="alert_dispatch",
                trigger_ref_id=str(alert.id),
                status="failed",
                execution_time_ms=0,
                result={"success": False, "message": error_message, "data": {"missing_params": missing_params}},
                error_message=error_message,
            )
            db.add(exec_log)

            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                integration_id=integration.id,
                target_id=str(target_id) if target_id is not None else None,
                target_name=target_name,
                channel=f"integration:{integration.integration_id}",
                recipient=target_name,
                status="failed",
                sent_at=now(),
                error_message=error_message,
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)
            await db.commit()
            continue

        try:
            result = await executor.execute_notification(integration.code, params, payload)
            execution_time_ms = int((now() - start_time).total_seconds() * 1000)

            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type="subscription_target",
                target_ref=str(target_id) if target_id is not None else None,
                subscription_id=subscription.id,
                target_name=target_name,
                params_snapshot=params,
                payload_summary={"alert_id": alert.id, "severity": alert.severity},
                trigger_source="alert_dispatch",
                trigger_ref_id=str(alert.id),
                status="success" if result.get("success") else "failed",
                execution_time_ms=execution_time_ms,
                result=result,
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(exec_log)

            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                integration_id=integration.id,
                target_id=str(target_id) if target_id is not None else None,
                target_name=target_name,
                channel=f"integration:{integration.integration_id}",
                recipient=target_name,
                status="sent" if result.get("success") else "failed",
                sent_at=now(),
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)
            await db.commit()

        except Exception as e:
            logger.error(f"Integration 执行异常: {str(e)}", exc_info=True)
            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type="subscription_target",
                target_ref=str(target_id) if target_id is not None else None,
                subscription_id=subscription.id,
                target_name=target_name,
                params_snapshot=params,
                payload_summary={"alert_id": alert.id, "severity": alert.severity},
                trigger_source="alert_dispatch",
                trigger_ref_id=str(alert.id),
                status="failed",
                execution_time_ms=0,
                error_message=str(e)
            )
            db.add(exec_log)

            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                integration_id=integration.id,
                target_id=str(target_id) if target_id is not None else None,
                target_name=target_name,
                channel=f"integration:{integration.integration_id}",
                recipient=target_name,
                status="failed",
                sent_at=now(),
                error_message=str(e)
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)
            await db.commit()

    return delivery_logs


async def _send_recovery_via_integration(db, alert, subscription):
    """通过 Integration 系统发送恢复通知"""
    from backend.models.integration import Integration, IntegrationExecutionLog
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from backend.models.datasource import Datasource
    from backend.services.integration_executor import IntegrationExecutor
    from sqlalchemy import select
    from datetime import datetime

    delivery_logs = []

    datasource = None
    diagnosis_summary = None
    if alert.datasource_id:
        ds_result = await db.execute(
            select(Datasource).where(Datasource.id == alert.datasource_id, alive_filter(Datasource))
        )
        datasource = ds_result.scalar_one_or_none()
    if alert.event_id:
        from backend.models.alert_event import AlertEvent

        event_result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert.event_id))
        event = event_result.scalar_one_or_none()
        diagnosis_summary = getattr(event, "ai_diagnosis_summary", None) if event else None

    for target in (subscription.integration_targets or []):
        if not isinstance(target, dict):
            continue
        if not target.get("enabled", True):
            continue
        if "recovery" not in (target.get("notify_on") or ["alert", "recovery"]):
            continue

        integration_id = target.get("integration_id")
        if not integration_id:
            continue

        integration = await get_alive_by_id(db, Integration, int(integration_id))
        if not integration or not integration.is_enabled:
            logger.warning(f"Integration {integration_id} 不存在或已禁用")
            continue

        payload = _build_recovery_alert_payload(alert, datasource, diagnosis_summary)

        params = target.get("params") or {}
        target_id = target.get("target_id")
        target_name = target.get("name") or integration.name
        required_params = _get_required_integration_params(integration)
        missing_params = [key for key in required_params if not params.get(key)]
        executor = IntegrationExecutor(db, logger)
        start_time = now()

        if missing_params:
            missing_params_text = ", ".join(missing_params)
            error_message = f"Integration 缺少必填参数: {missing_params_text}"
            logger.warning(
                "跳过恢复通知 target=%s integration=%s subscription=%s，原因：%s",
                target_name,
                integration.integration_id,
                subscription.id,
                error_message,
            )

            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type="subscription_target",
                target_ref=str(target_id) if target_id is not None else None,
                subscription_id=subscription.id,
                target_name=target_name,
                params_snapshot=params,
                payload_summary={"alert_id": alert.id, "status": "resolved"},
                trigger_source="alert_recovery",
                trigger_ref_id=str(alert.id),
                status="failed",
                execution_time_ms=0,
                result={"success": False, "message": error_message, "data": {"missing_params": missing_params}},
                error_message=error_message,
            )
            db.add(exec_log)

            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                integration_id=integration.id,
                target_id=str(target_id) if target_id is not None else None,
                target_name=target_name,
                channel=f"integration:{integration.integration_id}:recovery",
                recipient=target_name,
                status="failed",
                sent_at=now(),
                error_message=error_message,
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)
            await db.commit()
            continue

        try:
            result = await executor.execute_notification(integration.code, params, payload)
            execution_time_ms = int((now() - start_time).total_seconds() * 1000)

            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type="subscription_target",
                target_ref=str(target_id) if target_id is not None else None,
                subscription_id=subscription.id,
                target_name=target_name,
                params_snapshot=params,
                payload_summary={"alert_id": alert.id, "status": "resolved"},
                trigger_source="alert_recovery",
                trigger_ref_id=str(alert.id),
                status="success" if result.get("success") else "failed",
                execution_time_ms=execution_time_ms,
                result=result,
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(exec_log)

            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                integration_id=integration.id,
                target_id=str(target_id) if target_id is not None else None,
                target_name=target_name,
                channel=f"integration:{integration.integration_id}:recovery",
                recipient=target_name,
                status="sent" if result.get("success") else "failed",
                sent_at=now(),
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)
            await db.commit()

        except Exception as e:
            logger.error(f"Integration 执行异常: {str(e)}", exc_info=True)
            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type="subscription_target",
                target_ref=str(target_id) if target_id is not None else None,
                subscription_id=subscription.id,
                target_name=target_name,
                params_snapshot=params,
                payload_summary={"alert_id": alert.id, "status": "resolved"},
                trigger_source="alert_recovery",
                trigger_ref_id=str(alert.id),
                status="failed",
                execution_time_ms=0,
                error_message=str(e)
            )
            db.add(exec_log)

            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                integration_id=integration.id,
                target_id=str(target_id) if target_id is not None else None,
                target_name=target_name,
                channel=f"integration:{integration.integration_id}:recovery",
                recipient=target_name,
                status="failed",
                sent_at=now(),
                error_message=str(e)
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)
            await db.commit()

    return delivery_logs


async def _is_datasource_silenced(db, datasource_id: int) -> bool:
    """Check if a datasource is currently in silence period"""
    from sqlalchemy import select
    from backend.models.datasource import Datasource
    from backend.utils.datetime_helper import now

    result = await db.execute(
        select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
    )
    datasource = result.scalar_one_or_none()

    if not datasource or not datasource.silence_until:
        return False

    current_time = now()
    if current_time < datasource.silence_until:
        return True

    # Silence period expired, clear it
    datasource.silence_until = None
    datasource.silence_reason = None
    await db.commit()
    return False


def _is_historical_alert(alert) -> bool:
    created_at = getattr(alert, "created_at", None)
    if not created_at:
        return False
    cutoff = now() - timedelta(days=MAX_ALERT_HISTORY_DAYS)
    return created_at < cutoff


def _is_network_probe_alert(alert) -> bool:
    return getattr(alert, "metric_name", None) == NETWORK_PROBE_METRIC_NAME


def _should_skip_for_probe_failure(alert, has_probe_failure: bool) -> bool:
    return has_probe_failure and not _is_network_probe_alert(alert)


async def _has_active_network_probe_failure(db) -> bool:
    from backend.models.alert_message import AlertMessage
    from sqlalchemy import and_

    result = await db.execute(
        select(AlertMessage.id).where(
            and_(
                AlertMessage.alert_type == "system_error",
                AlertMessage.metric_name == NETWORK_PROBE_METRIC_NAME,
                AlertMessage.status.in_(["active", "acknowledged"]),
            )
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _process_recovery_notifications(db):
    """Send notifications for recently resolved alerts"""
    resolved_alerts = await AlertService.get_pending_recovery_notifications(db, minutes=60)

    if not resolved_alerts:
        return

    logger.debug(f"Processing {len(resolved_alerts)} recovery notifications")

    subscriptions = await AlertService.get_all_subscriptions(db)
    if not subscriptions:
        return

    has_probe_failure = await _has_active_network_probe_failure(db)

    for alert in resolved_alerts:
        if _is_historical_alert(alert):
            logger.info(
                "Skipping recovery for alert %s: historical alert older than %s days",
                alert.id,
                MAX_ALERT_HISTORY_DAYS,
            )
            continue

        if _should_skip_for_probe_failure(alert, has_probe_failure):
            logger.info(
                "Skipping recovery for alert %s: active network probe failure, only %s alert can be sent",
                alert.id,
                NETWORK_PROBE_METRIC_NAME,
            )
            continue

        # Check if datasource is in silence period
        if await _is_datasource_silenced(db, alert.datasource_id):
            logger.debug(f"Skipping recovery notification for alert {alert.id}: datasource {alert.datasource_id} is silenced")
            continue

        for subscription in subscriptions:
            try:
                if not await NotificationService.check_subscription_match(alert, subscription):
                    continue

                # Recovery should only go to subscriptions that received
                # the original alert notification.
                if not await AlertService.has_alert_notification_for_subscription(
                    db, alert.id, subscription.id
                ):
                    logger.debug(
                        "Skipping recovery notification for alert %s subscription %s: "
                        "original alert was never delivered",
                        alert.id,
                        subscription.id,
                    )
                    continue

                # Check if recovery notification already sent for this alert + subscription
                if await AlertService.has_recovery_notification_for_subscription(
                    db, alert.id, subscription.id
                ):
                    continue

                delivery_logs = await _send_recovery_via_integration(
                    db, alert, subscription
                )

                logger.info(
                    f"Sent {len(delivery_logs)} recovery notifications for alert {alert.id} "
                    f"(subscription {subscription.id})"
                )

            except Exception as e:
                logger.error(
                    f"Error processing recovery for alert {alert.id} subscription {subscription.id}: {e}",
                    exc_info=True
                )
