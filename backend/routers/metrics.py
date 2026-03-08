from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from datetime import datetime

from backend.database import get_db
from backend.models.metric_snapshot import MetricSnapshot
from backend.schemas.metrics import MetricResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)])


@router.get("/{conn_id}", response_model=List[MetricResponse])
async def get_metrics(
    conn_id: int,
    metric_type: Optional[str] = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    query = select(MetricSnapshot).where(MetricSnapshot.datasource_id == conn_id)
    if metric_type:
        query = query.where(MetricSnapshot.metric_type == metric_type)
    query = query.order_by(desc(MetricSnapshot.collected_at)).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{conn_id}/latest", response_model=Optional[MetricResponse])
async def get_latest_metric(
    conn_id: int,
    metric_type: str = "db_status",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == conn_id,
            MetricSnapshot.metric_type == metric_type,
        )
        .order_by(desc(MetricSnapshot.collected_at))
        .limit(1)
    )
    return result.scalar_one_or_none()
