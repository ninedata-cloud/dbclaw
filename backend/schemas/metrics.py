from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class MetricData(BaseModel):
    connection_id: int
    metric_type: str
    data: dict
    collected_at: Optional[datetime] = None


class MetricQuery(BaseModel):
    metric_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 100


class MetricResponse(BaseModel):
    id: int
    connection_id: int
    metric_type: str
    data: Any
    collected_at: Optional[datetime] = None

    class Config:
        from_attributes = True
