import asyncio
import logging
import re
from datetime import timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

from backend.utils.datetime_helper import now

from backend.models.alert_message import AlertMessage
from backend.models.alert_subscription import AlertSubscription
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.schemas.alert import (
    AlertMessageCreate,
    AlertMessageResponse,
    AlertSubscriptionCreate,
    AlertSubscriptionResponse,
    AlertQueryParams,
    IntegrationTarget,
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
            title = f"{metric_name} 阈值告警"
        else:
            title = f"{alert_type.replace('_', ' ').title()}"

        # Generate content
        content_parts = []
        if metric_name and metric_value is not None:
            content_parts.append(f"指标：{metric_name} = {metric_value:.2f}")
        if threshold_value is not None:
            content_parts.append(f"阈值：{threshold_value:.2f}")
        if trigger_reason:
            content_parts.append(f"原因：{trigger_reason}")

        content = "\n".join(content_parts) if content_parts else "告警已触发"

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
            status="active",
            created_at=now(),
            updated_at=now()
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
        alert.acknowledged_at = now()
        alert.updated_at = now()

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
        alert.resolved_at = now()
        alert.updated_at = now()
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
            alive_select(AlertSubscription).where(AlertSubscription.enabled == True)
        )
        return result.scalars().all()

    @staticmethod
    async def get_user_subscriptions(
        db: AsyncSession,
        user_id: int
    ) -> List[AlertSubscription]:
        """Get all subscriptions for a user"""
        result = await db.execute(
            alive_select(AlertSubscription).where(AlertSubscription.user_id == user_id)
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
            channel_ids=[],
            integration_targets=[target.model_dump() for target in subscription_data.integration_targets],
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
        subscription = await get_alive_by_id(db, AlertSubscription, subscription_id)

        if not subscription:
            return None

        # Convert time_ranges if present
        if 'time_ranges' in update_data and update_data['time_ranges']:
            update_data['time_ranges'] = [
                tr.model_dump() if hasattr(tr, 'model_dump') else tr
                for tr in update_data['time_ranges']
            ]

        if 'integration_targets' in update_data and update_data['integration_targets'] is not None:
            update_data['integration_targets'] = [
                t.model_dump() if hasattr(t, 'model_dump') else t
                for t in update_data['integration_targets']
            ]

        for key, value in update_data.items():
            if value is not None:
                setattr(subscription, key, value)

        subscription.updated_at = now()

        await db.commit()
        await db.refresh(subscription)

        logger.info(f"Updated subscription {subscription_id}")
        return subscription

    @staticmethod
    async def delete_subscription(
        db: AsyncSession,
        subscription_id: int,
        user_id: int | None = None
    ) -> bool:
        """Soft delete an alert subscription"""
        subscription = await get_alive_by_id(db, AlertSubscription, subscription_id)

        if not subscription:
            return False

        subscription.soft_delete(user_id)
        subscription.updated_at = now()
        await db.commit()

        logger.info(f"Soft deleted subscription {subscription_id}")
        return True

    @staticmethod
    async def get_pending_notifications(
        db: AsyncSession,
        minutes: int = 10
    ) -> List[AlertMessage]:
        """
        Get active alerts that haven't been notified yet.

        Only returns alerts where notified_at is NULL, meaning they have
        never been successfully notified. This prevents the same alert
        from being sent repeatedly across dispatcher cycles.

        Args:
            db: Database session
            minutes: Time window (kept for API compatibility, no longer used for filtering)

        Returns:
            List of alerts that need notification
        """
        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.status == "active",
                    AlertMessage.notified_at.is_(None)
                )
            )
        )
        return result.scalars().all()

    @staticmethod
    async def get_pending_recovery_notifications(
        db: AsyncSession,
        minutes: int = 60
    ) -> List[AlertMessage]:
        """
        Get recently resolved alerts that need recovery notifications.

        Args:
            db: Database session
            minutes: Only consider alerts resolved within this window

        Returns:
            List of resolved alerts within the time window
        """
        cutoff_time = now() - timedelta(minutes=minutes)

        # Get recently resolved alerts
        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.status == "resolved",
                    AlertMessage.resolved_at >= cutoff_time
                )
            )
        )
        return result.scalars().all()

    @staticmethod
    async def has_recovery_notification_for_subscription(
        db: AsyncSession,
        alert_id: int,
        subscription_id: int
    ) -> bool:
        """
        Check if a recovery notification has already been sent for a specific
        alert + subscription combination.

        Args:
            db: Database session
            alert_id: Alert ID
            subscription_id: Subscription ID

        Returns:
            True if recovery notification already sent
        """
        delivery_result = await db.execute(
            select(AlertDeliveryLog).where(
                and_(
                    AlertDeliveryLog.alert_id == alert_id,
                    AlertDeliveryLog.subscription_id == subscription_id,
                    AlertDeliveryLog.channel.like("%recovery%"),
                    AlertDeliveryLog.status == "sent"
                )
            )
        )
        return delivery_result.scalars().first() is not None

    @staticmethod
    async def trigger_auto_diagnosis(db: AsyncSession, alert_event_id: int) -> Optional[str]:
        """
        Trigger AI auto-diagnosis for an alert event and return the diagnosis summary.
        Creates a hidden diagnostic session, runs diagnosis skills, and saves the summary.

        Args:
            db: Database session
            alert_event_id: The alert event ID to diagnose

        Returns:
            AI-generated diagnosis summary string, or None if diagnosis failed
        """
        from backend.models.alert_event import AlertEvent
        from backend.models.diagnostic_session import DiagnosticSession
        from backend.models.datasource import Datasource
        from backend.models.soft_delete import alive_filter
        from backend.database import async_session as db_session_factory

        # Get alert event
        result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_event_id))
        event = result.scalar_one_or_none()
        if not event:
            logger.warning(f"Alert event {alert_event_id} not found for auto-diagnosis")
            return None

        # Get datasource
        result = await db.execute(select(Datasource).where(Datasource.id == event.datasource_id, alive_filter(Datasource)))
        ds = result.scalar_one_or_none()
        if not ds:
            logger.warning(f"Datasource {event.datasource_id} not found for auto-diagnosis")
            return None

        # Build diagnosis context
        severity_emoji = "🔴" if event.severity == "critical" else "🟠" if event.severity == "high" else "🟡"
        draft = f"""{severity_emoji} 告警：{event.title}

级别：{event.severity}
类型：{event.alert_type or '未知'}
指标：{event.metric_name or '未知'}
首次时间：{event.event_start_time.isoformat() if event.event_start_time else '未知'}
持续时间：{(now() - event.event_start_time).total_seconds() / 60:.0f} 分钟（截至目前）

请分析此告警的根本原因并给出处置建议。请按以下格式输出（使用 Markdown）：

## 根本原因
<分析为什么会出现这个问题，可能的原因有哪些>

## 处置建议
<具体的修复步骤，列出 1-5 条可操作的建议>

"""

        # Create hidden diagnostic session
        session = DiagnosticSession(
            datasource_id=event.datasource_id,
            user_id=None,  # System session
            title=f"自动诊断: {event.title[:40]}",
            is_hidden=True,  # Hidden from user session list
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.info(f"Created auto-diagnosis session {session.id} for alert event {alert_event_id}")

        # Run AI diagnosis asynchronously (non-blocking)
        # The diagnosis will update the alert_event.ai_diagnosis_summary field
        asyncio.create_task(_run_auto_diagnosis(session.id, alert_event_id, ds.id, ds.db_type, draft))

        return f"正在诊断中（会话 {session.id}）..."


async def _run_auto_diagnosis(session_id: int, alert_event_id: int, datasource_id: int, db_type: str, draft: str):
    """
    Run auto-diagnosis for a given session (background, non-blocking).
    Reuses _run_diagnosis_coro and saves extracted structured results.
    """
    from backend.models.alert_event import AlertEvent
    from backend.database import async_session as db_session_factory

    try:
        diagnosis_text = await _run_diagnosis_coro(session_id, alert_event_id, datasource_id, db_type, draft)

        if diagnosis_text:
            async with db_session_factory() as db:
                from sqlalchemy import update
                root_cause, recommended_actions, summary = _extract_diagnosis_parts(diagnosis_text)
                await db.execute(
                    update(AlertEvent)
                    .where(AlertEvent.id == alert_event_id)
                    .values(
                        ai_diagnosis_summary=summary,
                        root_cause=root_cause,
                        recommended_actions=recommended_actions,
                        diagnosis_status="completed",
                    )
                )
                await db.commit()
                logger.info(f"Auto-diagnosis complete for alert event {alert_event_id}: {diagnosis_text[:100]}...")
        else:
            logger.warning(f"Auto-diagnosis returned empty result for alert event {alert_event_id}")
    except Exception as e:
        logger.error(f"Auto-diagnosis failed for alert event {alert_event_id}: {e}", exc_info=True)


def _extract_diagnosis_parts(full_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse AI diagnosis text to extract root_cause, recommended_actions, and summary.

    Returns:
        (root_cause, recommended_actions, summary)
    """
    if not full_text:
        return None, None, None

    root_cause = None
    recommended_actions = None

    # Try markdown section headers first
    sections = {}

    # Split by markdown headers (## or ###)
    header_pattern = re.compile(r'^#{1,3}\s*(.+?)\s*$', re.MULTILINE)
    parts = header_pattern.split(full_text)
    if len(parts) > 1:
        # parts[0] is before first header, parts[1] is first header name, parts[2] is content, etc.
        for i in range(1, len(parts), 2):
            header = parts[i].strip().lower()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections[header] = content

    # Normalize header keys for matching
    root_cause_keys = ['根本原因', 'root cause', '原因分析', '问题原因', 'causes', 'cause']
    action_keys = ['处置建议', 'recommendations', '建议', '修复建议', '操作建议', 'actions', 'action', '修复步骤', '下一步']

    for header, content in sections.items():
        if root_cause is None:
            for key in root_cause_keys:
                if key in header:
                    root_cause = content.strip()
                    break
        if recommended_actions is None:
            for key in action_keys:
                if key in header:
                    recommended_actions = content.strip()
                    break

    # Fallback: if no structured sections found, try keyword detection
    if root_cause is None:
        text_lower = full_text.lower()
        # Try to find content after root cause keywords anywhere in text
        for keyword in ['根本原因', '原因分析', '可能原因', '问题原因']:
            pattern = re.compile(rf'{re.escape(keyword)}[：:]\s*(.+?)(?=\n\n|\n##|\n#|\Z)', re.DOTALL | re.IGNORECASE)
            match = pattern.search(full_text)
            if match:
                root_cause = match.group(1).strip()[:500]
                break

    if recommended_actions is None:
        for keyword in ['处置建议', '修复建议', '建议', '修复步骤', '下一步', '操作建议']:
            pattern = re.compile(rf'{re.escape(keyword)}[：:]\s*(.+?)(?=\n\n|\n##|\n#|\Z)', re.DOTALL | re.IGNORECASE)
            match = pattern.search(full_text)
            if match:
                recommended_actions = match.group(1).strip()[:500]
                break

    # Summary: strip markdown and truncate
    summary = full_text.strip()[:2000]

    return root_cause, recommended_actions, summary


async def run_sync_diagnosis(
    db: AsyncSession,
    alert_event_id: int,
    timeout_seconds: int = 600
) -> Dict[str, Any]:
    """
    Perform synchronous AI diagnosis for an alert event with timeout control.
    Creates a diagnostic session, runs AI analysis, extracts root cause and
    recommended actions, and saves results to the alert event.

    Args:
        db: Database session
        alert_event_id: The alert event ID to diagnose
        timeout_seconds: Maximum time to wait for diagnosis (default 60s)

    Returns:
        Dict with keys: root_cause, recommended_actions, summary, status
    """
    from backend.models.alert_event import AlertEvent
    from backend.models.diagnostic_session import DiagnosticSession
    from backend.models.datasource import Datasource

    # Get alert event
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_event_id))
    event = result.scalar_one_or_none()
    if not event:
        logger.warning(f"Alert event {alert_event_id} not found for sync diagnosis")
        return {"root_cause": None, "recommended_actions": None, "summary": None, "status": "failed"}

    # If diagnosis already completed, return cached result
    if event.diagnosis_status == "completed" and event.ai_diagnosis_summary:
        logger.info(f"Using cached diagnosis for alert event {alert_event_id}")
        return {
            "root_cause": event.root_cause,
            "recommended_actions": event.recommended_actions,
            "summary": event.ai_diagnosis_summary,
            "status": "completed",
        }

    # Get datasource
    result = await db.execute(select(Datasource).where(Datasource.id == event.datasource_id, alive_filter(Datasource)))
    ds = result.scalar_one_or_none()
    if not ds:
        logger.warning(f"Datasource {event.datasource_id} not found for sync diagnosis")
        return {"root_cause": None, "recommended_actions": None, "summary": None, "status": "failed"}

    # Get latest metric value from related alert messages
    metric_value = event.metric_name  # fallback
    threshold_value = None
    from backend.models.alert_message import AlertMessage
    from sqlalchemy import select as sa_select
    alert_result = await db.execute(
        sa_select(AlertMessage)
        .where(AlertMessage.event_id == alert_event_id)
        .order_by(AlertMessage.created_at.desc())
        .limit(1)
    )
    latest_alert = alert_result.scalar_one_or_none()
    if latest_alert:
        metric_value = f"{latest_alert.metric_name}={latest_alert.metric_value}" if latest_alert.metric_name else None
        threshold_value = latest_alert.threshold_value

    # Update status to in_progress
    event.diagnosis_status = "in_progress"
    await db.commit()

    # Build structured diagnosis prompt
    severity_emoji = "🔴" if event.severity == "critical" else "🟠" if event.severity == "high" else "🟡"
    metric_info = f"{metric_value}" if metric_value else "未知"
    threshold_info = f"阈值: {threshold_value}" if threshold_value else ""

    draft = f"""{severity_emoji} 告警：{event.title}

级别：{event.severity}
类型：{event.alert_type or '未知'}
指标：{metric_info}
{threshold_info}
首次时间：{event.event_start_time.isoformat() if event.event_start_time else '未知'}
持续时间：{(now() - event.event_start_time).total_seconds() / 60:.0f} 分钟

请分析此告警的根本原因并给出处置建议。请按以下格式输出（使用 Markdown）：

## 根本原因
<分析为什么会出现这个问题，可能的原因有哪些>

## 处置建议
<具体的修复步骤，列出 1-5 条可操作的建议>

"""

    # Create hidden diagnostic session
    session = DiagnosticSession(
        datasource_id=event.datasource_id,
        user_id=None,
        title=f"告警诊断: {event.title[:40]}",
        is_hidden=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(f"Running sync diagnosis for alert event {alert_event_id}, session {session.id}")

    try:
        # Run diagnosis with timeout
        diagnosis_text = await asyncio.wait_for(
            _run_diagnosis_coro(session.id, alert_event_id, ds.id, ds.db_type, draft),
            timeout=timeout_seconds,
        )

        # Extract structured parts
        root_cause, recommended_actions, summary = _extract_diagnosis_parts(diagnosis_text)

        # Save all fields to alert event
        event.ai_diagnosis_summary = summary
        event.root_cause = root_cause
        event.recommended_actions = recommended_actions
        event.diagnosis_status = "completed"
        await db.commit()

        logger.info(f"Sync diagnosis complete for alert event {alert_event_id}")
        return {
            "root_cause": root_cause,
            "recommended_actions": recommended_actions,
            "summary": summary,
            "status": "completed",
        }

    except asyncio.TimeoutError:
        logger.warning(f"Sync diagnosis timed out after {timeout_seconds}s for alert event {alert_event_id}")
        event.diagnosis_status = "pending"
        await db.commit()
        return {
            "root_cause": None,
            "recommended_actions": None,
            "summary": "诊断超时，正在后台继续分析...",
            "status": "pending",
        }
    except Exception as e:
        logger.error(f"Sync diagnosis failed for alert event {alert_event_id}: {e}", exc_info=True)
        event.diagnosis_status = "failed"
        await db.commit()
        return {
            "root_cause": None,
            "recommended_actions": None,
            "summary": f"诊断失败: {str(e)[:200]}",
            "status": "failed",
        }


async def _run_diagnosis_coro(
    session_id: int,
    alert_event_id: int,
    datasource_id: int,
    db_type: str,
    draft: str,
) -> str:
    """
    Core async coroutine to run AI diagnosis and return the full text.
    Used by both sync and async diagnosis paths.
    """
    from backend.database import async_session as db_session_factory
    from backend.agent.conversation_skills import run_conversation_with_skills
    from backend.models.alert_event import AlertEvent
    from backend.services.chat_orchestration_service import prepare_user_turn
    from sqlalchemy import select
    from backend.models.diagnostic_session import ChatMessage

    async with db_session_factory() as db:
        # Save user message first
        await prepare_user_turn(db, session_id=session_id, user_id=None, user_message=draft)

        # Build messages for AI
        result = await db.execute(
            alive_select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        all_msgs = result.scalars().all()

        messages = []
        for m in all_msgs:
            if m.role == "user":
                messages.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                messages.append({"role": "assistant", "content": m.content})
            elif m.role == "tool_call":
                import json as json_module
                try:
                    data = json_module.loads(m.content)
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": data.get("tool_call_id") or f"call_{data['tool_name']}_{m.id}",
                            "type": "function",
                            "function": {"name": data["tool_name"], "arguments": json_module.dumps(data["tool_args"])}
                        }]
                    })
                except Exception:
                    pass

        # Run conversation (non-streaming, collect final response)
        full_diagnosis = ""
        async for event in run_conversation_with_skills(
            messages,
            datasource_id,
            None,
            None,
            db,
            user_id=None,
            session_id=session_id,
            disabled_tools=[],
        ):
            event_type = event.get("type")
            if event_type == "content":
                full_diagnosis += event["content"]
            elif event_type == "done":
                break
            elif event_type == "error":
                break

        return full_diagnosis
