from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class AlertAIEvaluationLog(Base):
    __tablename__ = "alert_ai_evaluation_logs"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    policy_id = Column(Integer, nullable=True, index=True)
    policy_source = Column(String(20), nullable=False, default="inline")
    policy_fingerprint = Column(String(64), nullable=False, index=True)
    model_id = Column(Integer, nullable=True)
    mode = Column(String(20), nullable=False, default="formal", index=True)  # formal, shadow, preview
    decision = Column(String(20), nullable=True, index=True)  # alert, no_alert, recover
    confidence = Column(Float, nullable=True)
    severity = Column(String(20), nullable=True)
    policy_severity_hint = Column(String(20), nullable=True)
    severity_source = Column(String(20), nullable=True, index=True)  # explicit, inferred, invalid
    trigger_inspection = Column(Boolean, nullable=False, default=False)
    accepted = Column(Boolean, nullable=False, default=False, index=True)
    error_message = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)
    feature_summary = Column(JSON, nullable=True)
    raw_response = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
