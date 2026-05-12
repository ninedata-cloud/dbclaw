from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from backend.database import Base


class EvalSuite(Base):
    """A named collection of evaluation cases."""
    __tablename__ = "eval_suite"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    case_ids = Column(JSONB, nullable=False, default=list)
    is_builtin = Column(String(8), nullable=False, default="no")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EvalRun(Base):
    """A single execution of a suite against a model."""
    __tablename__ = "eval_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    suite_id = Column(Integer, nullable=True, index=True)
    suite_name = Column(String(120), nullable=True)
    ai_model_id = Column(Integer, nullable=True)
    ai_model_name = Column(String(120), nullable=True)
    judge_model_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    total_cases = Column(Integer, nullable=False, default=0)
    completed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    total_score = Column(Numeric(10, 2), nullable=True)
    dimension_summary = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class EvalCaseResult(Base):
    """Per-case result inside a run."""
    __tablename__ = "eval_case_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)
    case_id = Column(String(120), nullable=False, index=True)
    case_title = Column(String(200), nullable=True)
    case_category = Column(String(60), nullable=True)
    session_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending")
    score = Column(Numeric(10, 2), nullable=True)
    dimension_scores = Column(JSONB, nullable=True)
    judge_feedback = Column(JSONB, nullable=True)
    tool_call_summary = Column(JSONB, nullable=True)
    conclusion_md = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
