"""
Datasource Importance Models
数据库重要性自动分级模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.database import Base


class DatasourceImportance(Base):
    """数据库重要性评分表 - AI 自动分级"""
    __tablename__ = "datasource_importance"

    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), primary_key=True)
    importance_score = Column(Float)  # 0-100 自动计算
    importance_tier = Column(String(20))  # CRITICAL, IMPORTANT, NORMAL

    # 评分因子（自动采集）
    connection_frequency = Column(Float, default=0.0)
    query_volume = Column(Float, default=0.0)
    business_hours_activity = Column(Float, default=0.0)
    data_change_rate = Column(Float, default=0.0)
    downstream_dependencies = Column(Integer, default=0)
    historical_incidents = Column(Integer, default=0)
    user_interaction_count = Column(Integer, default=0)

    # 监控策略（自动调整）
    collection_interval = Column(Integer, default=15)  # 5s/15s/60s
    anomaly_detection_mode = Column(String(20), default='batch')  # realtime/neartime/batch
    auto_fix_enabled = Column(Boolean, default=False)

    last_recalculated = Column(DateTime, default=datetime.utcnow)
    score_history = Column(JSON)  # 历史评分记录

    # Relationships
    datasource = relationship("Datasource", back_populates="importance")

    def __repr__(self):
        return f"<DatasourceImportance(datasource_id={self.datasource_id}, tier={self.importance_tier}, score={self.importance_score})>"
