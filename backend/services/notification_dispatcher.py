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

                            # Send notifications
                            delivery_logs = await NotificationService.send_notifications(
                                db, alert, subscription
                            )

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
        for subscription in subscriptions:
            try:
                if not await NotificationService.check_subscription_match(alert, subscription):
                    continue

                delivery_logs = await NotificationService.send_recovery_notifications(
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
