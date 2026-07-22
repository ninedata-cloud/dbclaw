from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class User(SoftDeleteMixin, Base):
    __tablename__ = "app_user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    locale = Column(String(35), nullable=False, default="zh-CN", server_default="zh-CN")
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai", server_default="Asia/Shanghai")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    session_version = Column(Integer, nullable=False, default=1)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
