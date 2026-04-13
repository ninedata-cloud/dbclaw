from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class AlertAIRuntimeState(Base):
    __tablename__ = "alert_ai_runtime_states"
    __table_args__ = (
        UniqueConstraint("datasource_id", "policy_fingerprint", name="ux_alert_ai_runtime_states_datasource_policy"),
    )

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    policy_id = Column(Integer, nullable=True, index=True)
    policy_source = Column(String(20), nullable=False, default="inline")
    policy_fingerprint = Column(String(64), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=False, index=True)
    consecutive_alert_count = Column(Integer, nullable=False, default=0)
    consecutive_recover_count = Column(Integer, nullable=False, default=0)
    cooldown_until = Column(DateTime, nullable=True, index=True)
    last_decision = Column(String(20), nullable=True)
    last_confidence = Column(Float, nullable=True)
    last_reason = Column(Text, nullable=True)
    last_evidence = Column(JSON, nullable=True)
    last_candidate_type = Column(String(32), nullable=True, index=True)
    last_candidate_fingerprint = Column(String(128), nullable=True)
    last_ai_evaluated_at = Column(DateTime, nullable=True, index=True)
    last_gate_reason = Column(String(64), nullable=True)
    last_gate_metrics = Column(JSON, nullable=True)
    samples_seen = Column(Integer, nullable=False, default=0)
    candidate_hits = Column(Integer, nullable=False, default=0)
    ai_evaluations = Column(Integer, nullable=False, default=0)
    gate_skips_by_reason = Column(JSON, nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True, index=True)
    last_triggered_at = Column(DateTime, nullable=True, index=True)
    last_recovered_at = Column(DateTime, nullable=True, index=True)
    alert_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
