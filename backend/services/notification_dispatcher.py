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

logger = logging.getLogger(__name__)


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
                            if not subscription.channel_ids:
                                logger.warning(
                                    f"Subscription {subscription.id} has no channels configured, skipping"
                                )
                                continue

                            # Pre-send dedup: check if already delivered for this alert+subscription
                            if await _already_delivered(db, alert.id, subscription.id):
                                logger.debug(
                                    f"Skipping alert {alert.id} for subscription {subscription.id}: already delivered"
                                )
                                continue

                            delivery_logs = await _send_via_integrations(
                                db, alert, subscription
                            )

                            # Mark alert as notified after first successful send
                            if delivery_logs and any(l.status == "sent" for l in delivery_logs):
                                await _mark_alert_notified(db, alert)

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


async def _mark_alert_notified(db, alert):
    """Mark alert as notified so it won't be picked up again"""
    from datetime import datetime
    alert.notified_at = datetime.now()
    await db.commit()


async def _send_via_integrations(db, alert, subscription):
    """通过 Integration 系统发送通知"""
    from backend.models.integration import AlertChannel, Integration, IntegrationExecutionLog
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from backend.models.datasource import Datasource
    from backend.services.integration_executor import IntegrationExecutor
    from sqlalchemy import select
    from datetime import datetime

    delivery_logs = []

    # 获取数据源信息
    datasource = None
    if alert.datasource_id:
        ds_result = await db.execute(
            select(Datasource).where(Datasource.id == alert.datasource_id)
        )
        datasource = ds_result.scalar_one_or_none()

    # 遍历所有 Channel
    for channel_id in subscription.channel_ids:
        # 查询 Channel
        channel = await db.get(AlertChannel, channel_id)
        if not channel or not channel.enabled:
            logger.warning(f"Channel {channel_id} 不存在或已禁用")
            continue

        # 查询 Integration
        integration = await db.get(Integration, channel.integration_id)
        if not integration or not integration.enabled:
            logger.warning(f"Integration {channel.integration_id} 不存在或已禁用")
            continue

        # 构建 payload
        payload = {
            "title": f"【{alert.severity.upper()}】{datasource.name if datasource else '未知数据源'} 告警",
            "content": alert.content,
            "severity": alert.severity,
            "datasource_name": datasource.name if datasource else "未知数据源",
            "alert_id": alert.id,
            "timestamp": alert.created_at.isoformat() if alert.created_at else datetime.utcnow().isoformat()
        }

        # 执行 Integration
        executor = IntegrationExecutor(db, logger)
        start_time = datetime.utcnow()

        try:
            result = await executor.execute_notification(
                integration.code,
                channel.params,
                payload
            )

            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # 记录执行日志
            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                channel_id=channel.id,
                trigger_source="alert_dispatch",
                trigger_ref_id=str(alert.id),
                status="success" if result.get("success") else "failed",
                execution_time_ms=execution_time_ms,
                result=result,
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(exec_log)

            # 记录告警投递日志
            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                channel=f"integration:{integration.integration_id}",
                recipient=channel.name,
                status="sent" if result.get("success") else "failed",
                sent_at=datetime.utcnow(),
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)

            await db.commit()

            if result.get("success"):
                logger.info(f"通过 Integration {integration.name} 发送通知成功")
            else:
                logger.error(f"通过 Integration {integration.name} 发送通知失败: {result.get('message')}")

        except Exception as e:
            logger.error(f"Integration 执行异常: {str(e)}", exc_info=True)

            # 记录失败日志
            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                channel_id=channel.id,
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
                channel=f"integration:{integration.integration_id}",
                recipient=channel.name,
                status="failed",
                sent_at=datetime.utcnow(),
                error_message=str(e)
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)

            await db.commit()

    return delivery_logs


async def _send_recovery_via_integrations(db, alert, subscription):
    """通过 Integration 系统发送恢复通知"""
    from backend.models.integration import AlertChannel, Integration, IntegrationExecutionLog
    from backend.models.alert_delivery_log import AlertDeliveryLog
    from backend.models.datasource import Datasource
    from backend.services.integration_executor import IntegrationExecutor
    from sqlalchemy import select
    from datetime import datetime

    delivery_logs = []

    # 获取数据源信息
    datasource = None
    if alert.datasource_id:
        ds_result = await db.execute(
            select(Datasource).where(Datasource.id == alert.datasource_id)
        )
        datasource = ds_result.scalar_one_or_none()

    # 遍历所有 Channel
    for channel_id in subscription.channel_ids:
        # 查询 Channel
        channel = await db.get(AlertChannel, channel_id)
        if not channel or not channel.enabled:
            logger.warning(f"Channel {channel_id} 不存在或已禁用")
            continue

        # 查询 Integration
        integration = await db.get(Integration, channel.integration_id)
        if not integration or not integration.enabled:
            logger.warning(f"Integration {channel.integration_id} 不存在或已禁用")
            continue

        # 构建恢复通知 payload
        resolved_at = alert.resolved_at.isoformat() if alert.resolved_at else datetime.utcnow().isoformat()
        payload = {
            "title": f"【已恢复】{datasource.name if datasource else '未知数据源'} 告警已恢复",
            "content": f"{alert.content}\n\n告警时间：{alert.created_at.isoformat() if alert.created_at else '未知'}\n恢复时间：{resolved_at}",
            "severity": "info",  # 恢复通知使用 info 级别
            "datasource_name": datasource.name if datasource else "未知数据源",
            "alert_id": alert.id,
            "timestamp": resolved_at,
            "status": "resolved"
        }

        # 执行 Integration
        executor = IntegrationExecutor(db, logger)
        start_time = datetime.utcnow()

        try:
            result = await executor.execute_notification(
                integration.code,
                channel.params,
                payload
            )

            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # 记录执行日志
            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                channel_id=channel.id,
                trigger_source="alert_recovery",
                trigger_ref_id=str(alert.id),
                status="success" if result.get("success") else "failed",
                execution_time_ms=execution_time_ms,
                result=result,
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(exec_log)

            # 记录告警投递日志
            delivery_log = AlertDeliveryLog(
                alert_id=alert.id,
                subscription_id=subscription.id,
                channel=f"integration:{integration.integration_id}:recovery",
                recipient=channel.name,
                status="sent" if result.get("success") else "failed",
                sent_at=datetime.utcnow(),
                error_message=result.get("message") if not result.get("success") else None
            )
            db.add(delivery_log)
            delivery_logs.append(delivery_log)

            await db.commit()

            if result.get("success"):
                logger.info(f"通过 Integration {integration.name} 发送恢复通知成功")
            else:
                logger.error(f"通过 Integration {integration.name} 发送恢复通知失败: {result.get('message')}")

        except Exception as e:
            logger.error(f"Integration 执行异常: {str(e)}", exc_info=True)

            # 记录失败日志
            exec_log = IntegrationExecutionLog(
                integration_id=integration.id,
                channel_id=channel.id,
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
                channel=f"integration:{integration.integration_id}:recovery",
                recipient=channel.name,
                status="failed",
                sent_at=datetime.utcnow(),
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
        select(Datasource).where(Datasource.id == datasource_id)
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

                # Send recovery notifications via Integration system
                if not subscription.channel_ids:
                    logger.warning(
                        f"Subscription {subscription.id} has no channels configured, skipping recovery notification"
                    )
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
