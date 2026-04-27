from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func
from backend.database import Base


class InspectionConfig(Base):
    """Database inspection configuration with threshold rules and scheduling"""
    __tablename__ = "inspection_config"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, unique=True, nullable=False)
    is_enabled = Column("is_enabled", Boolean, default=True, nullable=False)

    # Scheduling
    schedule_interval = Column(Integer, default=86400, nullable=False)  # seconds, default daily
    last_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    next_scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # AI analysis
    use_ai_analysis = Column(Boolean, default=True, nullable=False)
    ai_model_id = Column(Integer, nullable=True)
    kb_ids = Column(JSON, default=list, nullable=False)  # array of KB IDs

    # Threshold rules (multi-level configuration)
    threshold_rules = Column(JSON, default=dict, nullable=False)
    # Example: {
    #   "cpu_usage": {
    #       "levels": [
    #           {"severity": "low", "threshold": 60, "duration": 300},
    #           {"severity": "medium", "threshold": 80, "duration": 60},
    #           {"severity": "high", "threshold": 85, "duration": 60},
    #           {"severity": "critical", "threshold": 90, "duration": 60}
    #       ]
    #   },
    #   "disk_usage": {
    #       "levels": [
    #           {"severity": "low", "threshold": 80, "duration": 0},
    #           {"severity": "medium", "threshold": 85, "duration": 0},
    #           {"severity": "high", "threshold": 90, "duration": 0},
    #           {"severity": "critical", "threshold": 95, "duration": 0}
    #       ]
    #   },
    #   "memory_usage": {
    #       "levels": [
    #           {"severity": "medium", "threshold": 85, "duration": 60},
    #           {"severity": "high", "threshold": 90, "duration": 60},
    #           {"severity": "critical", "threshold": 95, "duration": 60}
    #       ]
    #   },
    #   "connections": {
    #       "levels": [
    #           {"severity": "low", "threshold": 20, "duration": 60},
    #           {"severity": "medium", "threshold": 30, "duration": 60},
    #           {"severity": "high", "threshold": 40, "duration": 60},
    #           {"severity": "critical", "threshold": 50, "duration": 60}
    #       ]
    #   }
    # }

    # Alert engine routing
    alert_engine_mode = Column(String(20), default="inherit", nullable=False)  # inherit, threshold, ai
    ai_policy_source = Column(String(20), default="inline", nullable=False)  # inline, template
    ai_policy_text = Column(Text, nullable=True)
    ai_policy_id = Column(Integer, nullable=True)
    alert_ai_model_id = Column(Integer, nullable=True)
    ai_shadow_enabled = Column(Boolean, default=False, nullable=False)
    baseline_config = Column(JSON, default=dict, nullable=False)
    event_ai_config = Column(JSON, default=dict, nullable=False)
    alert_template_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    enabled = synonym("is_enabled")
