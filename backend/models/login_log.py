from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func
from backend.database import Base


class LoginLog(Base):
    __tablename__ = "login_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    logged_in_at = Column("logged_in_at", DateTime(timezone=True), server_default=func.now(), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    is_success = Column("is_success", Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    login_time = synonym("logged_in_at")
    success = synonym("is_success")
