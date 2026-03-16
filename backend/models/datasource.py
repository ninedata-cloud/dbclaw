from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.database import Base


class Datasource(Base):
    __tablename__ = "datasources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(20), nullable=False)  # mysql, postgresql, mongodb, redis, sqlserver, oracle
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password_encrypted = Column(Text, nullable=True)
    database = Column(String(100), nullable=True)
    host_id = Column(Integer, nullable=True)
    extra_params = Column(Text, nullable=True)  # JSON string for additional params
    is_active = Column(Boolean, default=True)

    # 用户配置的重要等级
    importance_level = Column(String(20), default='production')  # core, production, development, temporary
    monitoring_interval = Column(Integer, default=60)  # 监控间隔（秒）

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships (using string references to avoid circular imports)
    alert_events = relationship("AlertEvent", back_populates="datasource", lazy="selectin")

