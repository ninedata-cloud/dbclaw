"""
Metric Baseline Models
自动学习的指标基线模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base


class MetricBaseline(Base):
    """指标基线表 - AI 自动学习"""
    __tablename__ = "metric_baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String(100), nullable=False)
    time_window = Column(String(20))  # 'hourly', 'daily', 'weekly'

    # 统计基线
    p50 = Column(Float)
    p95 = Column(Float)
    p99 = Column(Float)
    mean = Column(Float)
    stddev = Column(Float)

    # 动态阈值（自动计算）
    upper_threshold = Column(Float)
    lower_threshold = Column(Float)

    # 元数据
    sample_count = Column(Integer)
    last_updated = Column(DateTime, default=datetime.utcnow)
    confidence_score = Column(Float)  # 基线可信度 0-1

    # Relationships
    datasource = relationship("Datasource", back_populates="baselines")

    __table_args__ = (
        UniqueConstraint('datasource_id', 'metric_name', 'time_window', name='uix_baseline'),
    )

    def __repr__(self):
        return f"<MetricBaseline(datasource_id={self.datasource_id}, metric={self.metric_name}, window={self.time_window})>"
