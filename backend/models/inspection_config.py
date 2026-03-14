from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class InspectionConfig(Base):
    """Database inspection configuration with threshold rules and scheduling"""
    __tablename__ = "inspection_configs"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id"), unique=True, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)

    # Scheduling
    schedule_interval = Column(Integer, default=86400, nullable=False)  # seconds, default daily
    last_scheduled_at = Column(DateTime, nullable=True)
    next_scheduled_at = Column(DateTime, nullable=True)

    # AI analysis
    use_ai_analysis = Column(Boolean, default=True, nullable=False)
    ai_model_id = Column(Integer, nullable=True)
    kb_ids = Column(JSON, default=list, nullable=False)  # array of KB IDs

    # Threshold rules
    threshold_rules = Column(JSON, default=dict, nullable=False)
    # Example: {
    #   "cpu_usage": {"threshold": 80, "duration": 60},
    #   "disk_usage": {"threshold": 80, "duration": 300},
    #   "memory_usage": {"threshold": 85, "duration": 60},
    #   "connections": {"threshold": 100, "duration": 120}
    # }

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
