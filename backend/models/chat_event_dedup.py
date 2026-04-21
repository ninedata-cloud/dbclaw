from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class ChatEventDedup(Base):
    __tablename__ = "chat_event_dedup"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_type = Column(String(50), nullable=False, index=True)
    external_event_id = Column(String(255), nullable=True, index=True)
    external_message_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
