from sqlalchemy import BigInteger, Column, Integer, String, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class Report(SoftDeleteMixin, Base):
    __tablename__ = "report"
    __table_args__ = (
        Index('idx_report_datasource_id', 'datasource_id'),
        Index('idx_report_datasource_created_at', 'datasource_id', 'created_at'),
        Index('idx_report_status', 'status'),
        Index('idx_report_trigger_type', 'trigger_type'),
        Index('idx_report_created_at', 'created_at'),
        Index('idx_report_composite', 'datasource_id', 'status', 'trigger_type', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    report_type = Column(String(50), default="comprehensive")  # comprehensive, performance, security
    status = Column(String(20), default="generating")  # generating, completed, partial, timed_out, awaiting_confirm, failed
    summary = Column(Text, nullable=True)
    content_md = Column(Text, nullable=True)
    content_html = Column(Text, nullable=True)
    findings = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)  # Terminal timestamp once report leaves generating state

    # AI-related columns
    ai_model_id = Column(Integer, nullable=True)  # Which AI model was used
    kb_ids = Column(JSON, nullable=True)  # Knowledge bases used during analysis
    generation_method = Column(String(20), default="rule-based")  # "ai" or "rule-based"
    error_message = Column(Text, nullable=True)  # Error details if generation failed

    # Inspection trigger columns
    trigger_type = Column(String(20), nullable=True)  # 'scheduled', 'manual', 'anomaly'
    trigger_id = Column(Integer, nullable=True)
    alert_id = Column(BigInteger, nullable=True, index=True)
    trigger_reason = Column(String(500), nullable=True)  # e.g., "CPU 95% > 80% for 60s"

    # AI inspection columns
    skill_executions = Column(JSON, nullable=True)  # Audit trail of skills called
    ai_conversation_id = Column(Integer, nullable=True)  # Link to diagnostic_session
