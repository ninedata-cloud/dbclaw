from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func

from backend.database import Base


class AlertAIPolicy(Base):
    __tablename__ = "alert_ai_policy"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    rule_text = Column(Text, nullable=False)
    is_enabled = Column("is_enabled", Boolean, default=True, nullable=False, index=True)
    model_id = Column(Integer, nullable=True)
    analysis_strategy = Column(String(32), nullable=False, default="candidate_only")
    analysis_config = Column(JSON, nullable=False, default=dict)
    compiled_trigger_profile = Column(JSON, nullable=True)
    compile_status = Column(String(20), nullable=False, default="pending", index=True)
    compile_error = Column(Text, nullable=True)
    compiled_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    enabled = synonym("is_enabled")
