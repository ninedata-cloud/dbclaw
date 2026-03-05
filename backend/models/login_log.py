from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    login_time = Column(DateTime, server_default=func.now())
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, nullable=False)
