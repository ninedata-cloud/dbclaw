from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class AIModel(Base):
    __tablename__ = "ai_model"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    provider = Column(String, nullable=False)
    protocol = Column(String, nullable=False, default="openai")
    api_key_encrypted = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    context_window = Column(Integer, nullable=True)
    reasoning_effort = Column(String, nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
