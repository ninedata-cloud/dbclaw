"""
Notification dispatcher background task
Processes pending alerts and sends notifications based on subscriptions
"""

import asyncio
import logging
from typing import List

from backend.database import async_session
from backend.services.alert_service import AlertService
from backend.services.notification_service import NotificationService
from backend.services.aggregation_engine import AggregationEngine
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)


def _get_required_integration_params(integration) -> list[str]:
    """从 Integration config_schema 提取必填参数"""
    schema = integration.config_schema or {}
    required = schema.get("required") or []
    return [key for key in required if isinstance(key, str) and key.strip()]


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
        # Get active alerts that haven't been notified recently (last 10 minutes)
        alerts = await AlertService.get_pending_notifications(db, minutes=10)

        if alerts:
            logger.debug(f"Processing {len(alerts)} pending alerts")

            # Get all active subscriptions
            subscriptions = await AlertService.get_all_subscriptions(db)

            if not subscriptions:
                logger.debug("No active subscriptions found")
            else:
                # Process each alert
                for alert in alerts:
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
                            from backend.services.alert_service import run_sync_diagnosis
                            diagnosis_result = await run_sync_diagnosis(db, alert.event_id, timeout_seconds=600)
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
                            if await _already_delivered(db, alert.id, subscription.id):
                                logger.debug(
                                    f"Skipping alert {alert.id} for subscription {subscription.id}: already delivered"
                                )
                                continue

                            delivery_logs = await _send_via_integrations(
                                db, alert, subscription, diagnosis_result
                            )

                            # Mark alert as notified after first successful send
                            if delivery_logs and any(l.status == "sent" for l in delivery_logs):
                                await _mark_alert_notified(db, alert)
                                # Trigger async background diagnosis for deeper analysis (UI side)
                                if alert.event_id:
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




async def _already_delivered(db, alert_id: int, subscription_id: int) -> bool:
    """Check if a successful delivery already exists for this alert+subscription"""
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from sqlalchemy import select, and_

    result = await db.execute(
        select(AlertDeliveryLog.id).where(
            and_(
                AlertDeliveryLog.alert_id == alert_id,
                AlertDeliveryLog.subscription_id == subscription_id,
                AlertDeliveryLog.status == "sent"
            )
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


async def _send_via_integrations(db, alert, subscription, diagnosis_result=None):
    """通过 Integration 系统发送通知"""
    from backend.config import get_settings
    from backend.models.integration import Integration, IntegrationExecutionLog
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from backend.models.datasource import Datasource
    from backend.services.integration_executor import IntegrationExecutor
    from backend.services.public_share_service import PublicShareService
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
            report_url = f"{base_url}/api/inspections/reports/public/{linked_report.id}/page?token={report_token}"

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
        if not integration or not integration.enabled:
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

        payload = {
            "title": f"【{alert.severity.upper()}】{datasource.name if datasource else '未知数据源'} 告警",
            "content": alert.content,
            "severity": alert.severity,
            "datasource_name": datasource.name if datasource else "未知数据源",
            "alert_id": alert.id,
            "alert_url": alert_url,
            "report_url": report_url,
            "timestamp": alert.created_at.strftime('%Y-%m-%d %H:%M:%S') if alert.created_at else now().strftime('%Y-%m-%d %H:%M:%S'),
            "ai_diagnosis_summary": ai_diagnosis_summary,
            "root_cause": root_cause,
            "recommended_actions": recommended_actions,
            "diagnosis_status": diagnosis_status,
            "alert_type": alert.alert_type,
            "metric_name": alert.metric_name,
            "metric_value": alert.metric_value,
            "threshold_value": alert.threshold_value,
            "trigger_reason": alert.trigger_reason,
        }

        params = target.get("params") or {}
        target_id = target.get("target_id")
        target_name = target.get("name") or integration.name
        required_params = _get_required_integration_params(integration)
        missing_params = [key for key in required_params if not params.get(key)]
        executor = IntegrationExecutor(db, logger)
        start_time = datetime.utcnow()

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
            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

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


async def _send_recovery_via_integrations(db, alert, subscription):
    """通过 Integration 系统发送恢复通知"""
    from backend.models.integration import Integration, IntegrationExecutionLog
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from backend.models.datasource import Datasource
    from backend.services.integration_executor import IntegrationExecutor
    from sqlalchemy import select
    from datetime import datetime

    delivery_logs = []

    datasource = None
    if alert.datasource_id:
        ds_result = await db.execute(
            select(Datasource).where(Datasource.id == alert.datasource_id, alive_filter(Datasource))
        )
        datasource = ds_result.scalar_one_or_none()

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
        if not integration or not integration.enabled:
            logger.warning(f"Integration {integration_id} 不存在或已禁用")
            continue

        resolved_at_str = alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else now().strftime('%Y-%m-%d %H:%M:%S')
        recovery_metric_line = ""
        if alert.metric_name and alert.resolved_value is not None:
            recovery_metric_line = f"\n恢复时指标：{alert.metric_name} = {alert.resolved_value:.2f}"
        elif alert.metric_name and alert.metric_value is not None:
            recovery_metric_line = f"\n恢复时指标：{alert.metric_name} = {alert.metric_value:.2f}"

        # Map alert_type and severity to Chinese labels for display
        alert_type_labels = {
            'threshold_violation': '超过阈值',
            'custom_expression': '自定义表达式',
            'system_error': '系统错误'
        }
        severity_labels = {'critical': '严重', 'high': '高', 'medium': '中', 'low': '低'}
        alert_type_display = alert_type_labels.get(alert.alert_type, alert.alert_type)
        severity_display = severity_labels.get(alert.severity, alert.severity)

        payload = {
            "title": f"【已恢复】{datasource.name if datasource else '未知数据源'} 告警已恢复",
            "content": f"告警类型：{alert_type_display}\n严重程度：{severity_display}\n\n{alert.content}{recovery_metric_line}\n\n告警时间：{alert.created_at.strftime('%Y-%m-%d %H:%M:%S') if alert.created_at else '未知'}\n恢复时间：{resolved_at_str}",
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "datasource_name": datasource.name if datasource else "未知数据源",
            "alert_id": alert.id,
            "timestamp": resolved_at_str,
            "status": "resolved",
            "metric_name": alert.metric_name,
            "metric_value": alert.metric_value,
            "threshold_value": alert.threshold_value,
            "trigger_reason": alert.trigger_reason,
        }

        params = target.get("params") or {}
        target_id = target.get("target_id")
        target_name = target.get("name") or integration.name
        required_params = _get_required_integration_params(integration)
        missing_params = [key for key in required_params if not params.get(key)]
        executor = IntegrationExecutor(db, logger)
        start_time = datetime.utcnow()

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
            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

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


async def _process_recovery_notifications(db):
    """Send notifications for recently resolved alerts"""
    resolved_alerts = await AlertService.get_pending_recovery_notifications(db, minutes=60)

    if not resolved_alerts:
        return

    logger.debug(f"Processing {len(resolved_alerts)} recovery notifications")

    subscriptions = await AlertService.get_all_subscriptions(db)
    if not subscriptions:
        return

    for alert in resolved_alerts:
        # Check if datasource is in silence period
        if await _is_datasource_silenced(db, alert.datasource_id):
            logger.debug(f"Skipping recovery notification for alert {alert.id}: datasource {alert.datasource_id} is silenced")
            continue

        for subscription in subscriptions:
            try:
                if not await NotificationService.check_subscription_match(alert, subscription):
                    continue

                # Check if recovery notification already sent for this alert + subscription
                if await AlertService.has_recovery_notification_for_subscription(
                    db, alert.id, subscription.id
                ):
                    continue

                delivery_logs = await _send_recovery_via_integrations(
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
