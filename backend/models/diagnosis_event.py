from sqlalchemy import BigInteger, Column, Integer, String, DateTime, JSON, Index
from sqlalchemy.sql import func

from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class DiagnosisEvent(SoftDeleteMixin, Base):
    __tablename__ = "diagnosis_event"
    __table_args__ = (
        Index('idx_diagnosis_event_session_run_sequence_id', 'session_id', 'run_id', 'sequence_no', 'id'),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    sequence_no = Column(Integer, nullable=False, default=0)
    step_id = Column(String(100), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
