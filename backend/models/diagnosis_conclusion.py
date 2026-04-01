from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean
from sqlalchemy.sql import func
from backend.database import Base


class DiagnosisConclusion(Base):
    """Structured diagnosis conclusion for sessions"""
    __tablename__ = "diagnosis_conclusions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    datasource_id = Column(Integer, nullable=True)

    # Structured findings
    findings = Column(JSON, nullable=True)  # [{severity, category, description, suggestion}]
    action_items = Column(JSON, nullable=True)  # [{title, priority, description}]

    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())