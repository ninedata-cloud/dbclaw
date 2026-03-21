from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import ast
import sys
from io import StringIO

from backend.models.alert_message import AlertMessage
from backend.models.alert_subscription import AlertSubscription
from backend.models.alert_delivery_log import AlertDeliveryLog

logger = logging.getLogger(__name__)


class AggregationEngine:
    """Alert aggregation logic to prevent notification storms"""

    @staticmethod
    async def should_send_alert(
        db: AsyncSession,
        alert: AlertMessage,
        subscription: AlertSubscription
    ) -> bool:
        """
        Evaluate aggregation rules to determine if alert should be sent.

        Args:
            db: Database session
            alert: Alert to evaluate
            subscription: Subscription configuration

        Returns:
            True if notification should be sent, False otherwise
        """
        # Check if custom script exists
        if subscription.aggregation_script:
            return await AggregationEngine.execute_custom_script(
                db, alert, subscription
            )

        # Default rule: 10-minute cooldown per datasource + alert_type
        return await AggregationEngine._default_aggregation_rule(
            db, alert, subscription
        )

    @staticmethod
    async def _default_aggregation_rule(
        db: AsyncSession,
        alert: AlertMessage,
        subscription: AlertSubscription
    ) -> bool:
        """
        Default aggregation rule:
        - If alert belongs to an event, only send notification for the first alert in the event,
          or if the last notification for this event was sent more than 60 minutes ago (re-notify).
        - Otherwise, use 60-minute cooldown per datasource + alert_type

        Args:
            db: Database session
            alert: Alert to evaluate
            subscription: Subscription configuration

        Returns:
            True if notification should be sent, False if suppressed
        """
        # 如果告警属于某个事件，检查该事件是否已经发送过通知
        if alert.event_id:
            # 查询该事件的所有告警的投递记录
            result = await db.execute(
                select(AlertDeliveryLog).join(
                    AlertMessage, AlertDeliveryLog.alert_id == AlertMessage.id
                ).where(
                    and_(
                        AlertDeliveryLog.subscription_id == subscription.id,
                        AlertMessage.event_id == alert.event_id,
                        AlertDeliveryLog.status == "sent"
                    )
                )
            )
            event_deliveries = result.scalars().all()

            if event_deliveries:
                # 检查最近一次投递是否超过60分钟，超过则允许重新通知
                latest_delivery = max(event_deliveries, key=lambda d: d.sent_at or d.created_at)
                latest_sent_at = latest_delivery.sent_at or latest_delivery.created_at
                minutes_since_last = (datetime.now() - latest_sent_at).total_seconds() / 60

                if minutes_since_last < 60:
                    logger.info(
                        f"Suppressing alert {alert.id} - event {alert.event_id} already has "
                        f"{len(event_deliveries)} notifications sent, last {minutes_since_last:.0f}m ago"
                    )
                    return False
                else:
                    logger.info(
                        f"Re-notifying for event {alert.event_id} - last notification was "
                        f"{minutes_since_last:.0f}m ago"
                    )
                    return True

        # 如果没有事件ID，使用传统的时间窗口聚合
        # 使用60分钟聚合窗口，避免频繁发送相同告警
        cutoff_time = datetime.now() - timedelta(minutes=60)

        # Check for recent deliveries with same datasource and alert_type
        result = await db.execute(
            select(AlertDeliveryLog).join(
                AlertMessage, AlertDeliveryLog.alert_id == AlertMessage.id
            ).where(
                and_(
                    AlertDeliveryLog.subscription_id == subscription.id,
                    AlertDeliveryLog.sent_at >= cutoff_time,
                    AlertDeliveryLog.status == "sent",
                    AlertMessage.datasource_id == alert.datasource_id,
                    AlertMessage.alert_type == alert.alert_type
                )
            )
        )
        recent_deliveries = result.scalars().all()

        if recent_deliveries:
            logger.info(
                f"Suppressing alert {alert.id} due to recent delivery "
                f"(datasource={alert.datasource_id}, type={alert.alert_type}, "
                f"found {len(recent_deliveries)} deliveries in last 60 minutes)"
            )
            return False

        return True

    @staticmethod
    async def execute_custom_script(
        db: AsyncSession,
        alert: AlertMessage,
        subscription: AlertSubscription
    ) -> bool:
        """
        Execute user-defined aggregation function.

        Args:
            db: Database session
            alert: Alert to evaluate
            subscription: Subscription configuration

        Returns:
            True if notification should be sent, False otherwise
        """
        try:
            # Prepare context data
            alert_info = {
                "datasource_id": alert.datasource_id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "metric_name": alert.metric_name,
                "metric_value": alert.metric_value,
                "threshold_value": alert.threshold_value,
                "title": alert.title,
                "content": alert.content
            }

            # Get delivery history for this subscription (last 24 hours)
            cutoff_time = datetime.now() - timedelta(hours=24)
            history_result = await db.execute(
                select(AlertDeliveryLog).where(
                    and_(
                        AlertDeliveryLog.subscription_id == subscription.id,
                        AlertDeliveryLog.created_at >= cutoff_time
                    )
                )
            )
            delivery_logs = history_result.scalars().all()
            delivery_history = [
                {
                    "sent_at": log.sent_at,
                    "channel": log.channel,
                    "status": log.status,
                    "alert_id": log.alert_id
                }
                for log in delivery_logs
            ]

            # Count similar alerts (same datasource + same alert_type in last 10 minutes)
            similar_cutoff = datetime.now() - timedelta(minutes=10)
            similar_result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.datasource_id == alert.datasource_id,
                        AlertMessage.alert_type == alert.alert_type,
                        AlertMessage.created_at >= similar_cutoff
                    )
                )
            )
            similar_alerts_count = len(similar_result.scalars().all())

            # Prepare current time info
            now = datetime.now()
            current_time = {
                "datetime": now,
                "hour": now.hour,
                "weekday": now.weekday(),
                "is_business_hours": (
                    9 <= now.hour < 18 and now.weekday() < 5
                )
            }

            # Execute custom script in sandboxed environment
            result = AggregationEngine._execute_sandboxed(
                subscription.aggregation_script,
                alert_info,
                delivery_history,
                similar_alerts_count,
                current_time
            )

            logger.info(
                f"Custom aggregation script for subscription {subscription.id} "
                f"returned: {result}"
            )
            return bool(result)

        except Exception as e:
            logger.error(
                f"Error executing custom aggregation script for subscription "
                f"{subscription.id}: {e}"
            )
            # On error, fall back to default rule
            return await AggregationEngine._default_aggregation_rule(
                db, alert, subscription
            )

    @staticmethod
    def _execute_sandboxed(
        script: str,
        alert_info: Dict[str, Any],
        delivery_history: List[Dict[str, Any]],
        similar_alerts_count: int,
        current_time: Dict[str, Any]
    ) -> bool:
        """
        Execute user script in sandboxed environment with timeout.

        Args:
            script: Python function code
            alert_info: Current alert information
            delivery_history: Recent delivery records
            similar_alerts_count: Number of similar alerts
            current_time: Current time information

        Returns:
            Boolean result from user function

        Raises:
            Exception: If script execution fails or times out
        """
        # Restricted globals - only allow safe builtins
        safe_globals = {
            "__builtins__": {
                "True": True,
                "False": False,
                "None": None,
                "len": len,
                "range": range,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "min": min,
                "max": max,
                "sum": sum,
                "any": any,
                "all": all,
            }
        }

        # Parse and validate script
        try:
            tree = ast.parse(script)
        except SyntaxError as e:
            raise ValueError(f"Script syntax error: {e}")

        # Execute script to define function
        local_namespace = {}
        exec(compile(tree, '<string>', 'exec'), safe_globals, local_namespace)

        # Find the should_send function
        if 'should_send' not in local_namespace:
            raise ValueError("Script must define a 'should_send' function")

        should_send_func = local_namespace['should_send']

        # Execute with timeout (5 seconds)
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("Script execution timeout (5 seconds)")

        # Set timeout (Unix only)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)

        try:
            result = should_send_func(
                alert_info,
                delivery_history,
                similar_alerts_count,
                current_time
            )
        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)  # Cancel alarm

        return result
