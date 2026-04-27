from sqlalchemy import BigInteger, Column, Integer, Numeric, DateTime, JSON, Index
from sqlalchemy.sql import func
from backend.database import Base
from backend.utils.datetime_helper import now


class HostMetric(Base):
    __tablename__ = "host_metric"
    __table_args__ = (
        Index('idx_host_metric_host_id_collected_at', 'host_id', 'collected_at'),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    host_id = Column(Integer, nullable=False, index=True)
    cpu_usage = Column(Numeric(22, 4), nullable=True)
    memory_usage = Column(Numeric(22, 4), nullable=True)
    disk_usage = Column(Numeric(22, 4), nullable=True)
    data = Column(JSON, nullable=True)  # 完整 OS 指标 JSON（含磁盘IO、网络IO、负载等）
    # 优先使用代码侧 UTC aware 时间，保留 server_default 兼容历史库结构
    collected_at = Column(DateTime(timezone=True), default=now, server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
