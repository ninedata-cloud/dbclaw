"""
Scheduled Report History Model

Tracks all scheduled report generation attempts with status and metrics.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base


class ScheduledReportHistory(Base):
    """Audit trail for scheduled report generations"""
    __tablename__ = "scheduled_report_history"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("scheduled_report_configs.id", ondelete="CASCADE"), nullable=False)
    report_id = Column(Integer, ForeignKey("reports.id", ondelete="SET NULL"), nullable=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    actual_generation_time = Column(DateTime, nullable=True)
    generation_duration_seconds = Column(Float, nullable=True)
    status = Column(String(20), nullable=False)  # completed, failed, skipped
    skip_reason = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    config = relationship("ScheduledReportConfig", back_populates="history")
    report = relationship("Report")
    datasource = relationship("Datasource")
