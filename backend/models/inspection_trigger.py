from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class InspectionTrigger(Base):
    """Audit trail of inspection events (scheduled/manual/anomaly)"""
    __tablename__ = "inspection_triggers"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    trigger_type = Column(String(20), nullable=False)  # 'scheduled', 'manual', 'anomaly', 'connection_failure'
    trigger_reason = Column(String(500), nullable=True)  # e.g., "CPU 95% > 80% for 60s"
    metric_snapshot = Column(JSON, nullable=True)  # metrics at trigger time
    triggered_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False)
    report_id = Column(Integer, nullable=True)
    alert_id = Column(Integer, nullable=True, index=True)
