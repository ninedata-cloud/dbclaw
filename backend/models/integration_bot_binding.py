from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class IntegrationBotBinding(Base):
    __tablename__ = "integration_bot_bindings"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, nullable=False, index=True)
    code = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    params = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
