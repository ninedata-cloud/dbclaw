from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func

from backend.database import Base


class AlertTemplate(Base):
    __tablename__ = "alert_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    is_enabled = Column("is_enabled", Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    template_config = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    enabled = synonym("is_enabled")
