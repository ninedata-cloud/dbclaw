"""
Alert Event Service

Handles aggregation of alerts into events and event management.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.models.datasource import Datasource
from backend.config import ALERT_AGGREGATION_TIME_WINDOW_MINUTES
from backend.utils.datetime_helper import now


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def infer_event_strategy(alert_type: str | None, metric_name: str | None) -> tuple[str, str]:
    metric = (metric_name or "").lower()
    alert_kind = (alert_type or "").lower()

    if alert_kind == "system_error" or metric == "connection_status":
        return "availability", "availability"
    if "disk" in metric or "storage" in metric:
        return "storage", "storage"
    if "replication" in metric or "lag" in metric:
        return "replication", "replication"
    if metric in {"cpu_usage", "memory_usage", "connections_active", "qps", "tps"}:
        return "performance", "performance"
    if alert_kind == "baseline_deviation":
        return "baseline", "performance"
    if alert_kind == "ai_policy_violation":
        return "ai_policy", "performance"
    return "general", "general"


def apply_event_diagnosis_lifecycle(
    event,
    *,
    stage: str,
    trigger_reason: str,
    refresh_needed: bool = True,
) -> None:
    event.lifecycle_stage = stage
    event.diagnosis_trigger_reason = trigger_reason
    event.is_diagnosis_refresh_needed = refresh_needed
    event.updated_at = now()


def hydrate_event_strategy_fields(event):
    if not event:
        return event
    if not getattr(event, "event_category", None) or not getattr(event, "fault_domain", None):
        event_category, fault_domain = infer_event_strategy(
            getattr(event, "alert_type", None),
            getattr(event, "metric_name", None),
        )
        if not getattr(event, "event_category", None):
            event.event_category = event_category
        if not getattr(event, "fault_domain", None):
            event.fault_domain = fault_domain
    if not getattr(event, "lifecycle_stage", None):
        status = getattr(event, "status", None)
        if status == "resolved":
            event.lifecycle_stage = "recovered"
        elif status == "acknowledged":
            event.lifecycle_stage = "acknowledged"
        else:
            event.lifecycle_stage = "active"
    return event


class AlertEventService:
    """Service for managing alert events"""

    @staticmethod
    def _status_priority_expr():
        return case(
            (AlertEvent.status == "active", 0),
            (AlertEvent.status == "acknowledged", 1),
            else_=2,
        )

    @staticmethod
    async def process_new_alert(
        db: AsyncSession,
        alert: AlertMessage,
        time_window_minutes: Optional[int] = None
    ) -> AlertEvent:
        """
        Process new alert into event system.

        Algorithm:
        1. Calculate aggregation keys (prefer metric_name, fallback to alert_type)
        2. Find recent events matching keys (within time window)
        3. If found and gap < time_window_minutes: add to existing event
        4. Else: create new event
        """
        if time_window_minutes is None:
            time_window_minutes = ALERT_AGGREGATION_TIME_WINDOW_MINUTES

        # Find matching event
        existing_event = await AlertEventService._find_matching_event(
            db, alert, time_window_minutes
        )

        if existing_event:
            # Add to existing event
            return await AlertEventService._add_alert_to_event(db, existing_event, alert)
        else:
            # Create new event
            aggregation_type = "by_metric_name" if alert.metric_name else "by_alert_type"
            return await AlertEventService._create_new_event(db, alert, aggregation_type)

    @staticmethod
    async def _find_matching_event(
        db: AsyncSession,
        alert: AlertMessage,
        time_window_minutes: int
    ) -> Optional[AlertEvent]:
        """Find existing event within time window"""
        # Calculate aggregation key (prefer metric_name)
        if alert.metric_name:
            aggregation_key = f"{alert.datasource_id}:{alert.metric_name}"
        else:
            aggregation_key = f"{alert.datasource_id}:{alert.alert_type}"

        # Calculate time threshold
        time_threshold = alert.created_at - timedelta(minutes=time_window_minutes)

        # Find matching event (only match active/acknowledged events, not resolved)
        result = await db.execute(
            select(AlertEvent)
            .where(
                and_(
                    AlertEvent.aggregation_key == aggregation_key,
                    AlertEvent.event_ended_at >= time_threshold,
                    AlertEvent.status.in_(["active", "acknowledged"])  # 只匹配未解决的事件
                )
            )
            .order_by(AlertEvent.event_ended_at.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def _create_new_event(
        db: AsyncSession,
        alert: AlertMessage,
        aggregation_type: str
    ) -> AlertEvent:
        """Create new event for alert"""
        # Calculate aggregation key
        if aggregation_type == "by_metric_name":
            aggregation_key = f"{alert.datasource_id}:{alert.metric_name}"
        else:
            aggregation_key = f"{alert.datasource_id}:{alert.alert_type}"

        event_category, fault_domain = infer_event_strategy(alert.alert_type, alert.metric_name)

        # Create event
        event = AlertEvent(
            datasource_id=alert.datasource_id,
            aggregation_key=aggregation_key,
            aggregation_type=aggregation_type,
            first_alert_id=alert.id,
            latest_alert_id=alert.id,
            alert_count=1,
            event_started_at=alert.created_at,
            event_ended_at=alert.created_at,
            updated_at=now(),
            status=alert.status,
            severity=alert.severity,
            title=alert.title,
            alert_type=alert.alert_type,
            metric_name=alert.metric_name,
            event_category=event_category,
            fault_domain=fault_domain,
            lifecycle_stage="created",
            is_diagnosis_refresh_needed=True,
            diagnosis_trigger_reason="event_created",
        )

        db.add(event)
        await db.flush()
        await db.refresh(event)

        return event

    @staticmethod
    async def _add_alert_to_event(
        db: AsyncSession,
        event: AlertEvent,
        alert: AlertMessage
    ) -> AlertEvent:
        """Add alert to existing event and update metadata"""
        # Update event metadata
        old_severity = event.severity
        event.latest_alert_id = alert.id
        event.alert_count += 1
        event.event_ended_at = alert.created_at
        event.updated_at = now()
        event.status = alert.status  # Inherit status from latest alert
        event.title = alert.title

        # Update severity (keep highest)
        if SEVERITY_ORDER.get(alert.severity, 0) > SEVERITY_ORDER.get(event.severity, 0):
            event.severity = alert.severity
            apply_event_diagnosis_lifecycle(
                event,
                stage="escalated",
                trigger_reason="severity_escalated",
            )
        else:
            event.lifecycle_stage = "active"

        if event.severity == old_severity and event.alert_type != alert.alert_type and not event.is_diagnosis_refresh_needed:
            event.diagnosis_trigger_reason = "event_updated"

        await db.flush()
        await db.refresh(event)

        return event

    @staticmethod
    async def get_events(
        db: AsyncSession,
        datasource_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Tuple[AlertEvent, Optional[Datasource]]], int]:
        """Query events with filters, returns list of (event, datasource) tuples"""
        # Build query with left join to datasource
        query = select(AlertEvent, Datasource).outerjoin(
            Datasource, AlertEvent.datasource_id == Datasource.id
        )
        count_query = select(func.count(AlertEvent.id))

        # Apply filters
        filters = []

        if datasource_ids:
            filters.append(AlertEvent.datasource_id.in_(datasource_ids))

        if start_time:
            filters.append(AlertEvent.event_started_at >= start_time)

        if end_time:
            filters.append(AlertEvent.event_ended_at <= end_time)

        if status and status != "all":
            filters.append(AlertEvent.status == status)

        if severity:
            filters.append(AlertEvent.severity == severity)

        if search:
            search_pattern = f"%{search}%"
            filters.append(
                or_(
                    AlertEvent.title.like(search_pattern),
                    AlertEvent.alert_type.like(search_pattern),
                    AlertEvent.metric_name.like(search_pattern)
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # Apply ordering
        if sort_by and sort_order:
            # Map sort fields to model attributes
            sort_field_map = {
                'severity': AlertEvent.severity,
                'datasource_id': AlertEvent.datasource_id,
                'fault_domain': AlertEvent.fault_domain,
                'lifecycle_stage': AlertEvent.lifecycle_stage,
                'event_started_at': AlertEvent.event_started_at,
                'event_ended_at': AlertEvent.event_ended_at,
                'duration': (AlertEvent.event_ended_at - AlertEvent.event_started_at),
                'status': AlertEvent.status,
            }

            sort_field = sort_field_map.get(sort_by)
            if sort_field is not None:
                if sort_order.lower() == 'asc':
                    query = query.order_by(sort_field.asc())
                else:
                    query = query.order_by(sort_field.desc())
            else:
                # Fallback to default ordering
                query = query.order_by(
                    AlertEventService._status_priority_expr().asc(),
                    AlertEvent.event_started_at.desc(),
                    AlertEvent.id.desc(),
                )
        else:
            # Default ordering
            query = query.order_by(
                AlertEventService._status_priority_expr().asc(),
                AlertEvent.event_started_at.desc(),
                AlertEvent.id.desc(),
            )

        query = query.limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        events_with_datasource = [
            (hydrate_event_strategy_fields(event), datasource)
            for event, datasource in result.all()
        ]

        return events_with_datasource, total

    @staticmethod
    async def get_alerts_in_event(
        db: AsyncSession,
        event_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[AlertMessage], int]:
        """Get all alerts in an event"""
        # Count query
        count_result = await db.execute(
            select(func.count(AlertMessage.id))
            .where(AlertMessage.event_id == event_id)
        )
        total = count_result.scalar()

        # Data query
        result = await db.execute(
            select(AlertMessage)
            .where(AlertMessage.event_id == event_id)
            .order_by(AlertMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        alerts = result.scalars().all()

        return alerts, total

    @staticmethod
    async def acknowledge_event(
        db: AsyncSession,
        event_id: int,
        user_id: int
    ) -> AlertEvent:
        """Acknowledge event and all its alerts"""
        # Get event
        result = await db.execute(
            select(AlertEvent).where(AlertEvent.id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event:
            raise ValueError(f"Event {event_id} not found")

        # Update event status
        event.status = "acknowledged"
        event.updated_at = now()

        # Update all alerts in event
        await db.execute(
            select(AlertMessage)
            .where(AlertMessage.event_id == event_id)
        )

        # Update alerts
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.event_id == event_id)
        )
        alerts = result.scalars().all()

        for alert in alerts:
            if alert.status == "active":
                alert.status = "acknowledged"
                alert.acknowledged_by = user_id
                alert.acknowledged_at = now()

        await db.flush()
        await db.refresh(event)

        return event

    @staticmethod
    async def resolve_event(
        db: AsyncSession,
        event_id: int
    ) -> AlertEvent:
        """Resolve event and all its alerts"""
        # Get event
        result = await db.execute(
            select(AlertEvent).where(AlertEvent.id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event:
            raise ValueError(f"Event {event_id} not found")

        # Update event status and end time
        now_time = now()
        event.status = "resolved"
        event.event_ended_at = now_time  # 更新恢复时间
        event.updated_at = now_time
        apply_event_diagnosis_lifecycle(
            event,
            stage="recovered",
            trigger_reason="event_recovered",
        )

        # Update all alerts in event
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.event_id == event_id)
        )
        alerts = result.scalars().all()

        for alert in alerts:
            if alert.status != "resolved":
                alert.status = "resolved"
                alert.resolved_at = now_time

        await db.flush()
        await db.refresh(event)

        return event

    @staticmethod
    async def update_active_event_time(
        db: AsyncSession,
        datasource_id: int,
        alert_type: Optional[str] = None,
        metric_name: Optional[str] = None
    ) -> Optional[AlertEvent]:
        """
        Update the event_ended_at time for an active event matching the criteria.
        Used when an alert condition persists but no new alert is created due to deduplication.

        Args:
            db: Database session
            datasource_id: Datasource ID
            alert_type: Alert type (optional, used if metric_name is not provided)
            metric_name: Metric name (optional, preferred over alert_type)

        Returns:
            Updated event if found and updated, None otherwise
        """
        # Calculate aggregation key (prefer metric_name)
        if metric_name:
            aggregation_key = f"{datasource_id}:{metric_name}"
        elif alert_type:
            aggregation_key = f"{datasource_id}:{alert_type}"
        else:
            return None

        # Find active event with this key
        result = await db.execute(
            select(AlertEvent)
            .where(
                and_(
                    AlertEvent.aggregation_key == aggregation_key,
                    AlertEvent.status.in_(["active", "acknowledged"])
                )
            )
            .order_by(AlertEvent.event_ended_at.desc())
            .limit(1)
        )
        event = result.scalar_one_or_none()

        if event:
            event.event_ended_at = now()
            event.updated_at = now()
            await db.flush()
            # 不在这里 commit，由调用方的 async_session 上下文管理器自动处理
            return event

        return None

    @staticmethod
    async def check_and_auto_resolve_event(
        db: AsyncSession,
        event_id: int
    ) -> Optional[AlertEvent]:
        """
        Check if all alerts in an event are resolved, and if so, auto-resolve the event.

        Args:
            db: Database session
            event_id: Event ID to check

        Returns:
            Updated event if it was auto-resolved, None otherwise
        """
        # Get event
        result = await db.execute(
            select(AlertEvent).where(AlertEvent.id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event or event.status == "resolved":
            return None

        # Get all alerts in event
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.event_id == event_id)
        )
        alerts = result.scalars().all()

        if not alerts:
            return None

        # Check if all alerts are resolved
        all_resolved = all(alert.status == "resolved" for alert in alerts)

        if all_resolved:
            # Auto-resolve the event
            now_time = now()
            event.status = "resolved"
            event.event_ended_at = now_time  # 更新恢复时间
            event.updated_at = now_time
            apply_event_diagnosis_lifecycle(
                event,
                stage="recovered",
                trigger_reason="event_recovered",
            )
            await db.flush()
            await db.refresh(event)
            return event

        return None
