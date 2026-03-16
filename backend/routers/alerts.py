from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from backend.database import get_db
from backend.services.alert_service import AlertService
from backend.services.alert_event_service import AlertEventService
from backend.services.notification_service import NotificationService
from backend.schemas.alert import (
    AlertMessageResponse,
    AlertQueryParams,
    AlertAcknowledgeRequest,
    AlertResolveRequest,
    AlertSubscriptionCreate,
    AlertSubscriptionUpdate,
    AlertSubscriptionResponse,
    TestNotificationRequest,
    AlertEventResponse,
    AlertEventQueryParams,
    AlertEventAcknowledgeRequest
)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=dict)
async def list_alerts(
    datasource_ids: Optional[str] = Query(None, description="Comma-separated datasource IDs"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    status: Optional[str] = Query("all", pattern="^(active|acknowledged|resolved|all)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List alerts with filters"""
    # Parse datasource_ids
    datasource_id_list = None
    if datasource_ids:
        try:
            datasource_id_list = [int(x.strip()) for x in datasource_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datasource_ids format")

    params = AlertQueryParams(
        datasource_ids=datasource_id_list,
        start_time=start_time,
        end_time=end_time,
        status=status,
        severity=severity,
        search=search,
        limit=limit,
        offset=offset
    )

    alerts, total = await AlertService.get_alerts(db, params)

    return {
        "alerts": [AlertMessageResponse.model_validate(alert) for alert in alerts],
        "total": total,
        "limit": limit,
        "offset": offset
    }


# Alert Event Endpoints (must be before /{alert_id} to avoid route conflicts)
@router.get("/events", response_model=dict)
async def list_alert_events(
    datasource_ids: Optional[str] = Query(None, description="Comma-separated datasource IDs"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    status: Optional[str] = Query("all", pattern="^(active|acknowledged|resolved|all)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List aggregated alert events with filters"""
    # Parse datasource_ids
    datasource_id_list = None
    if datasource_ids:
        try:
            datasource_id_list = [int(x.strip()) for x in datasource_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datasource_ids format")

    events, total = await AlertEventService.get_events(
        db=db,
        datasource_ids=datasource_id_list,
        start_time=start_time,
        end_time=end_time,
        status=status,
        severity=severity,
        search=search,
        limit=limit,
        offset=offset
    )

    return {
        "events": [AlertEventResponse.model_validate(event) for event in events],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/events/{event_id}/alerts", response_model=dict)
async def get_event_alerts(
    event_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get all alerts in an event"""
    alerts, total = await AlertEventService.get_alerts_in_event(
        db=db,
        event_id=event_id,
        limit=limit,
        offset=offset
    )

    return {
        "alerts": [AlertMessageResponse.model_validate(alert) for alert in alerts],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/events/{event_id}/acknowledge", response_model=AlertEventResponse)
async def acknowledge_event(
    event_id: int,
    request: AlertEventAcknowledgeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Acknowledge event and all its alerts"""
    try:
        event = await AlertEventService.acknowledge_event(db, event_id, request.user_id)
        await db.commit()
        return AlertEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/events/{event_id}/resolve", response_model=AlertEventResponse)
async def resolve_event(
    event_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Resolve event and all its alerts"""
    try:
        event = await AlertEventService.resolve_event(db, event_id)
        await db.commit()
        return AlertEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{alert_id}", response_model=AlertMessageResponse)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get alert details"""
    alert = await AlertService.get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertMessageResponse.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertMessageResponse)
async def acknowledge_alert(
    alert_id: int,
    request: AlertAcknowledgeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Acknowledge an alert"""
    alert = await AlertService.acknowledge_alert(db, alert_id, request.user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertMessageResponse.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertMessageResponse)
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Resolve an alert"""
    alert = await AlertService.resolve_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertMessageResponse.model_validate(alert)


@router.get("/subscriptions/list", response_model=List[AlertSubscriptionResponse])
async def list_subscriptions(
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """List user subscriptions"""
    subscriptions = await AlertService.get_user_subscriptions(db, user_id)
    return [AlertSubscriptionResponse.model_validate(sub) for sub in subscriptions]


@router.post("/subscriptions", response_model=AlertSubscriptionResponse)
async def create_subscription(
    subscription: AlertSubscriptionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new alert subscription"""
    created = await AlertService.create_subscription(db, subscription)
    return AlertSubscriptionResponse.model_validate(created)


@router.put("/subscriptions/{subscription_id}", response_model=AlertSubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    update_data: AlertSubscriptionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an alert subscription"""
    updated = await AlertService.update_subscription(
        db,
        subscription_id,
        update_data.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return AlertSubscriptionResponse.model_validate(updated)


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete an alert subscription"""
    success = await AlertService.delete_subscription(db, subscription_id)
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return {"message": "Subscription deleted successfully"}


@router.post("/subscriptions/{subscription_id}/test")
async def test_notification(
    subscription_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Test notification delivery for a subscription"""
    # Get subscription (including disabled ones for testing)
    from sqlalchemy import select as sa_select
    from backend.models.alert_subscription import AlertSubscription
    sub_result = await db.execute(
        sa_select(AlertSubscription).where(AlertSubscription.id == subscription_id)
    )
    subscription = sub_result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Create a test alert
    test_alert = await AlertService.create_alert(
        db=db,
        datasource_id=subscription.datasource_ids[0] if subscription.datasource_ids else 1,
        alert_type="system_error",
        severity="low",
        metric_name="test",
        metric_value=0.0,
        threshold_value=0.0,
        trigger_reason="Test notification"
    )

    # Send notifications
    delivery_logs = await NotificationService.send_notifications(
        db, test_alert, subscription
    )

    return {
        "message": "Test notification sent",
        "alert_id": test_alert.id,
        "deliveries": [
            {
                "channel": log.channel,
                "recipient": log.recipient,
                "status": log.status,
                "error_message": log.error_message
            }
            for log in delivery_logs
        ]
    }
