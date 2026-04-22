from sqlalchemy import Column, Integer, String, DateTime, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import func as sql_func

from backend.database import Base


class ChatChannelBinding(Base):
    __tablename__ = "chat_channel_binding"
    __table_args__ = (
        Index(
            'uq_chat_channel_binding_channel_chat_user',
            'channel_type',
            'external_chat_id',
            sql_func.coalesce('external_user_id', ''),
            unique=True
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_type = Column(String(50), nullable=False, index=True)
    external_chat_id = Column(String(255), nullable=False, index=True)
    external_user_id = Column(String(255), nullable=True, index=True)
    session_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    integration_id = Column(Integer, nullable=True, index=True)
    default_datasource_id = Column(Integer, nullable=True)
    default_model_id = Column(Integer, nullable=True)
    kb_ids = Column(JSON, nullable=True)
    disabled_tools = Column(JSON, nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
