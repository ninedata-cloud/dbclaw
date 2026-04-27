from sqlalchemy import BigInteger, Column, Integer, String, Boolean, DateTime, JSON, Text
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func
from backend.database import Base


class InspectionTrigger(Base):
    """Audit trail of inspection events (scheduled/manual/anomaly)"""
    __tablename__ = "inspection_trigger"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    trigger_type = Column(String(20), nullable=False)  # 'scheduled', 'manual', 'anomaly', 'connection_failure'
    trigger_reason = Column(String(500), nullable=True)  # e.g., "CPU 95% > 80% for 60s"
    datasource_metric = Column(JSON, nullable=True)  # metrics at trigger time
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    is_processed = Column("is_processed", Boolean, default=False, nullable=False)
    report_id = Column(Integer, nullable=True)
    alert_id = Column(BigInteger, nullable=True, index=True)
    error_message = Column(Text, nullable=True)  # 报告生成失败时的错误信息
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    processed = synonym("is_processed")
