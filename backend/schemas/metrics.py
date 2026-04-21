from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class MetricData(TimestampSerializerMixin, BaseModel):
    datasource_id: int
    metric_type: str
    data: dict
    collected_at: Optional[datetime] = None


class MetricQuery(BaseModel):
    metric_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 100


class MetricResponse(TimestampSerializerMixin, BaseModel):
    id: int
    datasource_id: int
    metric_type: str
    data: Any
    collected_at: Optional[datetime] = None

    class Config:
        from_attributes = True
