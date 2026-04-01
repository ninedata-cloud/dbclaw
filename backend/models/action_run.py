from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from backend.database import Base


class ActionRun(Base):
    __tablename__ = "action_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, nullable=False, index=True)
    alert_id = Column(Integer, nullable=True, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    recommendation_id = Column(String(100), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    risk_level = Column(String(20), nullable=False, default="safe")
    action_spec = Column(JSON, nullable=False)

    approval_id = Column(String(100), nullable=True, index=True)
    approval_status = Column(String(20), nullable=False, default="not_required")
    approved_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)

    skill_id = Column(String(100), nullable=True)
    skill_execution_id = Column(Integer, nullable=True, index=True)
    execution_status = Column(String(30), nullable=False, default="pending")
    execution_result_summary = Column(Text, nullable=True)

    verification_skill_id = Column(String(100), nullable=True)
    verification_skill_execution_id = Column(Integer, nullable=True, index=True)
    verification_status = Column(String(30), nullable=False, default="not_requested")
    verification_summary = Column(Text, nullable=True)

    status = Column(String(30), nullable=False, default="pending_approval", index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
