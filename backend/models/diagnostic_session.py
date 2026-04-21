from sqlalchemy import BigInteger, Column, Integer, String, DateTime, Text, JSON, Boolean
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class DiagnosticSession(SoftDeleteMixin, Base):
    __tablename__ = "diagnostic_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    datasource_id = Column(Integer, nullable=True)
    host_id = Column(Integer, nullable=True, index=True)
    ai_model_id = Column(Integer, nullable=True)
    title = Column(String(200), default="New Session")
    kb_ids = Column(JSON, nullable=True)
    knowledge_snapshot = Column(JSON, nullable=True)
    disabled_tools = Column(JSON, nullable=True)
    skill_authorizations = Column(JSON, nullable=True)
    is_hidden = Column(Boolean, default=False)  # System-created hidden sessions (e.g., auto-diagnosis)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(SoftDeleteMixin, Base):
    __tablename__ = "chat_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, tool_call, tool_result, approval_request, approval_response
    content = Column(Text, nullable=False)
    run_id = Column(String(64), nullable=True, index=True)
    render_segments = Column(JSON, nullable=True)
    status = Column(String(32), nullable=True)
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String(100), nullable=True)
    attachments = Column(JSON, nullable=True)  # List of attachment metadata
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
