"""
Scheduled Report Configuration Model

Stores configuration for automated report generation per datasource.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base


class ScheduledReportConfig(Base):
    """Configuration for scheduled report generation"""
    __tablename__ = "scheduled_report_configs"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False, unique=True)
    enabled = Column(Boolean, default=True, nullable=False)
    report_type = Column(String(50), default="comprehensive", nullable=False)
    schedule_interval = Column(Integer, nullable=False)  # in seconds
    use_ai_analysis = Column(Boolean, default=False, nullable=False)
    ai_model_id = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    kb_ids = Column(Text, nullable=True)  # JSON array of knowledge base IDs
    last_generated_at = Column(DateTime, nullable=True)
    next_scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    datasource = relationship("Datasource", back_populates="scheduled_report_config")
    ai_model = relationship("AIModel")
    history = relationship("ScheduledReportHistory", back_populates="config", cascade="all, delete-orphan")
