from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Numeric, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from backend.database import Base


class DiagnosisConclusion(Base):
    """Structured diagnosis conclusion for sessions"""
    __tablename__ = "diagnosis_conclusion"
    __table_args__ = (
        Index('idx_diagnosis_conclusion_session_updated_at_id', 'session_id', 'updated_at', 'id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    datasource_id = Column(Integer, nullable=True)
    run_id = Column(String(64), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    confidence = Column(Numeric(22, 4), nullable=True)
    final_markdown = Column(Text, nullable=True)

    # Structured findings
    findings = Column(JSONB, nullable=True)  # [{severity, category, description, suggestion}]
    action_items = Column(JSONB, nullable=True)  # [{title, priority, description}]
    evidence_refs = Column(JSONB, nullable=True)  # [{type, ref, title, detail}]
    knowledge_refs = Column(JSONB, nullable=True)  # [{document_id, title}]

    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())