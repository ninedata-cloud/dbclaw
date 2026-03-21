from sqlalchemy import Column, Integer, Float, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class HostMetric(Base):
    __tablename__ = "host_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, nullable=False, index=True)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    disk_usage = Column(Float, nullable=True)
    data = Column(JSON, nullable=True)  # 完整 OS 指标 JSON（含磁盘IO、网络IO、负载等）
    collected_at = Column(DateTime, server_default=func.now(), index=True)
