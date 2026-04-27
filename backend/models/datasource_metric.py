from sqlalchemy import BigInteger, Column, Integer, String, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from backend.database import Base


class DatasourceMetric(Base):
    __tablename__ = "datasource_metric"
    __table_args__ = (
        Index('idx_datasource_metric_composite', 'datasource_id', 'metric_type', 'collected_at'),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # db_status, os_metrics, slow_queries, etc.
    data = Column(JSON, nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=False, index=True)  # 移除 server_default，由代码显式设置本地时间
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
