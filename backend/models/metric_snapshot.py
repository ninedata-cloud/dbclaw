from sqlalchemy import Column, Integer, String, DateTime, Text, Float, JSON
from sqlalchemy.sql import func
from backend.database import Base


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(Integer, nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # db_status, os_metrics, slow_queries, etc.
    data = Column(JSON, nullable=False)
    collected_at = Column(DateTime, server_default=func.now(), index=True)
