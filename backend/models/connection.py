from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from backend.database import Base


class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(20), nullable=False)  # mysql, postgresql, mongodb, redis, sqlserver
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password_encrypted = Column(Text, nullable=True)
    database = Column(String(100), nullable=True)
    ssh_host_id = Column(Integer, nullable=True)
    extra_params = Column(Text, nullable=True)  # JSON string for additional params
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
