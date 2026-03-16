from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from backend.models.alert_message import AlertMessage
from backend.models.alert_subscription import AlertSubscription
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.schemas.alert import (
    AlertMessageCreate,
    AlertMessageResponse,
    AlertSubscriptionCreate,
    AlertSubscriptionResponse,
    AlertQueryParams
)

logger = logging.getLogger(__name__)


class AlertService:
    """Core alert management service"""

    @staticmethod
    def calculate_severity(percent_over: float) -> str:
        """
        Calculate alert severity based on percentage over threshold.

        Args:
            percent_over: Percentage over threshold (e.g., 25.0 means 25% over)

        Returns:
            Severity level: "critical", "high", "medium", or "low"
        """
        if percent_over > 100:
            return "critical"  # More than double the threshold
        elif percent_over > 50:
            return "high"      # 50-100% over threshold
        elif percent_over > 20:
            return "medium"    # 20-50% over threshold
        else:
            return "low"       # 0-20% over threshold

    @staticmethod
    async def create_alert(
        db: AsyncSession,
        datasource_id: int,
        alert_type: str,
        severity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        trigger_reason: Optional[str] = None
    ) -> AlertMessage:
        """
        Create a new alert message.

        Args:
            db: Database session
            datasource_id: ID of the datasource
            alert_type: Type of alert (threshold_violation, custom_expression, system_error)
            severity: Severity level (critical, high, medium, low)
            metric_name: Name of the metric (optional)
            metric_value: Current metric value (optional)
            threshold_value: Configured threshold (optional)
            trigger_reason: Detailed trigger reason (optional)

        Returns:
            Created AlertMessage instance
        """
        # Generate title based on alert type and metric
        if alert_type == "threshold_violation" and metric_name:
            title = f"{metric_name} threshold violation"
        else:
            title = f"{alert_type.replace('_', ' ').title()}"

        # Generate content
        content_parts = []
        if metric_name and metric_value is not None:
            content_parts.append(f"Metric: {metric_name} = {metric_value:.2f}")
        if threshold_value is not None:
            content_parts.append(f"Threshold: {threshold_value:.2f}")
        if trigger_reason:
            content_parts.append(f"Reason: {trigger_reason}")

        content = "\n".join(content_parts) if content_parts else "Alert triggered"

        alert = AlertMessage(
            datasource_id=datasource_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            content=content,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold_value=threshold_value,
            trigger_reason=trigger_reason,
            status="active"
        )

        db.add(alert)
        await db.commit()
        await db.refresh(alert)

        # Process into event
        from backend.services.alert_event_service import AlertEventService
        event = await AlertEventService.process_new_alert(db, alert)

        # Link alert to event
        alert.event_id = event.id
        await db.commit()
        await db.refresh(alert)

        logger.info(f"Created alert {alert.id}: {title} (severity: {severity}), event {event.id}")
        return alert

    @staticmethod
    async def get_alerts(
        db: AsyncSession,
        params: AlertQueryParams
    ) -> tuple[List[AlertMessage], int]:
        """
        Query alerts with filters.

        Args:
            db: Database session
            params: Query parameters

        Returns:
            Tuple of (alerts list, total count)
        """
        query = select(AlertMessage)
        count_query = select(AlertMessage)

        # Build filters
        filters = []

        if params.datasource_ids:
            filters.append(AlertMessage.datasource_id.in_(params.datasource_ids))

        if params.start_time:
            filters.append(AlertMessage.created_at >= params.start_time)

        if params.end_time:
            filters.append(AlertMessage.created_at <= params.end_time)

        if params.status and params.status != "all":
            filters.append(AlertMessage.status == params.status)

        if params.severity:
            filters.append(AlertMessage.severity == params.severity)

        if params.search:
            search_pattern = f"%{params.search}%"
            filters.append(
                or_(
                    AlertMessage.title.like(search_pattern),
                    AlertMessage.content.like(search_pattern)
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        # Apply ordering and pagination
        query = query.order_by(desc(AlertMessage.created_at))
        query = query.limit(params.limit).offset(params.offset)

        result = await db.execute(query)
        alerts = result.scalars().all()

        return alerts, total

    @staticmethod
    async def get_alert_by_id(db: AsyncSession, alert_id: int) -> Optional[AlertMessage]:
        """Get alert by ID"""
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.id == alert_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def acknowledge_alert(
        db: AsyncSession,
        alert_id: int,
        user_id: int
    ) -> Optional[AlertMessage]:
        """
        Mark alert as acknowledged.

        Args:
            db: Database session
            alert_id: Alert ID
            user_id: User who acknowledged the alert

        Returns:
            Updated AlertMessage or None if not found
        """
        alert = await AlertService.get_alert_by_id(db, alert_id)
        if not alert:
            return None

        alert.status = "acknowledged"
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.utcnow()
        alert.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert {alert_id} acknowledged by user {user_id}")
        return alert

    @staticmethod
    async def resolve_alert(
        db: AsyncSession,
        alert_id: int,
        resolved_value: Optional[float] = None
    ) -> Optional[AlertMessage]:
        """
        Mark alert as resolved.

        Args:
            db: Database session
            alert_id: Alert ID
            resolved_value: Metric value at time of recovery

        Returns:
            Updated AlertMessage or None if not found
        """
        alert = await AlertService.get_alert_by_id(db, alert_id)
        if not alert:
            return None

        alert.status = "resolved"
        alert.resolved_at = datetime.utcnow()
        alert.updated_at = datetime.utcnow()
        if resolved_value is not None:
            alert.resolved_value = resolved_value

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert {alert_id} resolved")

        # Check if parent event should be auto-resolved
        if alert.event_id:
            from backend.services.alert_event_service import AlertEventService
            resolved_event = await AlertEventService.check_and_auto_resolve_event(db, alert.event_id)
            if resolved_event:
                await db.commit()
                logger.info(f"Auto-resolved event {alert.event_id} after all alerts resolved")

        return alert

    @staticmethod
    async def get_all_subscriptions(db: AsyncSession) -> List[AlertSubscription]:
        """Get all active subscriptions"""
        result = await db.execute(
            select(AlertSubscription).where(AlertSubscription.enabled == True)
        )
        return result.scalars().all()

    @staticmethod
    async def get_user_subscriptions(
        db: AsyncSession,
        user_id: int
    ) -> List[AlertSubscription]:
        """Get all subscriptions for a user"""
        result = await db.execute(
            select(AlertSubscription).where(AlertSubscription.user_id == user_id)
        )
        return result.scalars().all()

    @staticmethod
    async def create_subscription(
        db: AsyncSession,
        subscription_data: AlertSubscriptionCreate
    ) -> AlertSubscription:
        """Create a new alert subscription"""
        # Convert time_ranges to dict format for JSON storage
        time_ranges_dict = [tr.model_dump() for tr in subscription_data.time_ranges]

        subscription = AlertSubscription(
            user_id=subscription_data.user_id,
            datasource_ids=subscription_data.datasource_ids,
            severity_levels=subscription_data.severity_levels,
            time_ranges=time_ranges_dict,
            channels=subscription_data.channels,
            webhook_url=subscription_data.webhook_url,
            enabled=subscription_data.enabled,
            aggregation_script=subscription_data.aggregation_script
        )

        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)

        logger.info(f"Created subscription {subscription.id} for user {subscription_data.user_id}")
        return subscription

    @staticmethod
    async def update_subscription(
        db: AsyncSession,
        subscription_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[AlertSubscription]:
        """Update an alert subscription"""
        result = await db.execute(
            select(AlertSubscription).where(AlertSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return None

        # Convert time_ranges if present
        if 'time_ranges' in update_data and update_data['time_ranges']:
            update_data['time_ranges'] = [
                tr.model_dump() if hasattr(tr, 'model_dump') else tr
                for tr in update_data['time_ranges']
            ]

        for key, value in update_data.items():
            if value is not None:
                setattr(subscription, key, value)

        subscription.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(subscription)

        logger.info(f"Updated subscription {subscription_id}")
        return subscription

    @staticmethod
    async def delete_subscription(
        db: AsyncSession,
        subscription_id: int
    ) -> bool:
        """Delete an alert subscription"""
        result = await db.execute(
            select(AlertSubscription).where(AlertSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return False

        await db.delete(subscription)
        await db.commit()

        logger.info(f"Deleted subscription {subscription_id}")
        return True

    @staticmethod
    async def get_pending_notifications(
        db: AsyncSession,
        minutes: int = 10
    ) -> List[AlertMessage]:
        """
        Get active alerts that haven't been notified recently.

        Args:
            db: Database session
            minutes: Time window to check for recent notifications

        Returns:
            List of alerts that need notification
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        # Get active alerts
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.status == "active")
        )
        alerts = result.scalars().all()

        # Filter out alerts that have recent successful deliveries
        pending_alerts = []
        for alert in alerts:
            # Check if there are recent successful deliveries
            delivery_result = await db.execute(
                select(AlertDeliveryLog).where(
                    and_(
                        AlertDeliveryLog.alert_id == alert.id,
                        AlertDeliveryLog.status == "sent",
                        AlertDeliveryLog.sent_at >= cutoff_time
                    )
                )
            )
            recent_deliveries = delivery_result.scalars().all()

            if not recent_deliveries:
                pending_alerts.append(alert)

        return pending_alerts

    @staticmethod
    async def get_pending_recovery_notifications(
        db: AsyncSession,
        minutes: int = 60
    ) -> List[AlertMessage]:
        """
        Get recently resolved alerts that haven't had a recovery notification sent yet.

        Args:
            db: Database session
            minutes: Only consider alerts resolved within this window

        Returns:
            List of resolved alerts needing recovery notification
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        # Get recently resolved alerts
        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.status == "resolved",
                    AlertMessage.resolved_at >= cutoff_time
                )
            )
        )
        resolved_alerts = result.scalars().all()

        # Filter out alerts that already have a recovery notification sent
        pending = []
        for alert in resolved_alerts:
            delivery_result = await db.execute(
                select(AlertDeliveryLog).where(
                    and_(
                        AlertDeliveryLog.alert_id == alert.id,
                        AlertDeliveryLog.channel == "recovery",
                        AlertDeliveryLog.status == "sent"
                    )
                )
            )
            recovery_logs = delivery_result.scalars().all()
            if not recovery_logs:
                pending.append(alert)

        return pending
