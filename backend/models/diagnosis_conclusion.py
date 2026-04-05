from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean, Float
from sqlalchemy.sql import func
from backend.database import Base


class DiagnosisConclusion(Base):
    """Structured diagnosis conclusion for sessions"""
    __tablename__ = "diagnosis_conclusions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    datasource_id = Column(Integer, nullable=True)
    run_id = Column(String(64), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    final_markdown = Column(Text, nullable=True)

    # Structured findings
    findings = Column(JSON, nullable=True)  # [{severity, category, description, suggestion}]
    action_items = Column(JSON, nullable=True)  # [{title, priority, description}]
    evidence_refs = Column(JSON, nullable=True)  # [{type, ref, title, detail}]
    knowledge_refs = Column(JSON, nullable=True)  # [{document_id, title}]

    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())