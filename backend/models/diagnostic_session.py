from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.database import Base


class DiagnosticSession(Base):
    __tablename__ = "diagnostic_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=True)
    ai_model_id = Column(Integer, ForeignKey("ai_models.id"), nullable=True)
    title = Column(String(200), default="New Session")
    kb_ids = Column(JSON, nullable=True)
    disabled_tools = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # AI Guardian relationships
    trained_rules = relationship("GuardianRule", back_populates="training_conversation")
    cases = relationship("DiagnosticCase", back_populates="diagnostic_conversation")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, tool
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String(100), nullable=True)
    attachments = Column(JSON, nullable=True)  # List of attachment metadata
    created_at = Column(DateTime, server_default=func.now())
