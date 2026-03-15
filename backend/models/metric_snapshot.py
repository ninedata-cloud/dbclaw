from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Text, Float, JSON
from backend.database import Base


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # db_status, os_metrics, slow_queries, etc.
    data = Column(JSON, nullable=False)
    collected_at = Column(DateTime, nullable=False, index=True)  # 移除 server_default，由代码显式设置本地时间
