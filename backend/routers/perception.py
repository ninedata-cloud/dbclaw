"""
Perception API - Health status and AI insights for datasources
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.services.ai_perception_service import (
    get_perception_status,
    get_datasource_health,
    subscribe,
    unsubscribe,
)
from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/perception", tags=["perception"])


@router.get("/status")
async def get_perception_status_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get overall perception status for all datasources.
    Returns health scores and anomalies based on active alerts (not baselines).
    """
    from backend.models.alert_message import AlertMessage
    from sqlalchemy import select

    # Get all active/acknowledged alerts grouped by datasource
    result = await db.execute(
        select(AlertMessage).where(
            AlertMessage.status.in_(["active", "acknowledged"])
        )
    )
    all_alerts = result.scalars().all()

    # Group alerts by datasource_id
    alerts_by_ds: Dict[int, List[AlertMessage]] = {}
    for alert in all_alerts:
        alerts_by_ds.setdefault(alert.datasource_id, []).append(alert)

    # Severity order for scoring
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def compute_health(alerts: List[AlertMessage]) -> tuple:
        """Compute health score and status from alerts."""
        if not alerts:
            return 100, "healthy"
        # Get highest severity
        severities = [a.severity for a in alerts if a.severity]
        if not severities:
            return 100, "healthy"
        highest = min(severities, key=lambda s: severity_order.get(s, 99))
        if highest == "critical":
            return 30, "critical"
        elif highest == "high":
            return 50, "degraded"
        elif highest == "medium":
            return 70, "warning"
        else:
            return 85, "warning"

    # Enrich with datasource info
    result = await db.execute(select(Datasource).where(Datasource.is_active == True))
    datasources = result.scalars().all()

    enriched_datasources = []
    for ds in datasources:
        ds_alerts = alerts_by_ds.get(ds.id, [])
        score, status = compute_health(ds_alerts)

        # Convert alerts to anomaly format for frontend compatibility
        anomalies = []
        for alert in sorted(ds_alerts, key=lambda a: severity_order.get(a.severity, 99)):
            anomalies.append({
                "severity": alert.severity,
                "metric_name": alert.metric_name or alert.alert_type,
                "current_value": alert.metric_value,
                "threshold": alert.threshold_value,
                "title": alert.title,
                "alert_type": alert.alert_type,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            })

        enriched_datasources.append({
            "id": ds.id,
            "name": ds.name,
            "db_type": ds.db_type,
            "host": ds.host,
            "importance_level": ds.importance_level,
            "health_score": score,
            "health_status": status,
            "anomalies": anomalies,
            "alert_count": len(anomalies),
        })

    return {
        "datasources": enriched_datasources,
        "total_alerts": len(all_alerts),
    }


@router.get("/datasources/{datasource_id}/insights")
async def get_datasource_insights(
    datasource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get AI-generated health insights for a specific datasource.
    """
    # Verify datasource exists
    result = await db.execute(
        select(Datasource).where(Datasource.id == datasource_id)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")

    health = get_datasource_health(datasource_id)

    return {
        "datasource_id": datasource_id,
        "datasource_name": ds.name,
        "db_type": ds.db_type,
        "health_score": health.get("score") if health else None,
        "health_status": health.get("status") if health else "unknown",
        "anomalies": health.get("anomalies", []) if health else [],
        "has_insights": health is not None and len(health.get("anomalies", [])) > 0,
    }


@router.get("/datasources")
async def list_datasources_health(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Get health status for all datasources (alias for status endpoint).
    """
    result = await db.execute(select(Datasource).where(Datasource.is_active == True))
    datasources = result.scalars().all()

    return [
        {
            "id": ds.id,
            "name": ds.name,
            "db_type": ds.db_type,
            "host": ds.host,
            "importance_level": ds.importance_level,
            **(
                {"health_score": health["score"], "health_status": health["status"], "anomalies": health.get("anomalies", [])}
                if (health := get_datasource_health(ds.id))
                else {"health_score": None, "health_status": "no_data", "anomalies": []}
            ),
        }
        for ds in datasources
    ]