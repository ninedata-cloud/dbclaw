"""
Anomaly Detection Models
异常检测记录模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from backend.database import Base


class Anomaly(Base):
    """异常检测记录表"""
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow)

    # 异常详情
    anomaly_type = Column(String(50))  # statistical, pattern, predictive, correlation
    affected_metrics = Column(JSON)
    severity = Column(String(20))  # CRITICAL, WARNING, INFO
    confidence = Column(Float)  # AI 置信度

    # 上下文
    baseline_value = Column(Float)
    current_value = Column(Float)
    deviation_percent = Column(Float)
    context_snapshot = Column(JSON)

    # AI 分析
    ai_diagnosis = Column(Text)
    root_cause = Column(Text)
    recommended_actions = Column(JSON)

    # 处理状态
    status = Column(String(20), default='detected')  # detected, diagnosing, resolved, false_positive
    resolved_at = Column(DateTime)
    resolution_actions = Column(JSON)
    was_auto_fixed = Column(Boolean, default=False)

    # 学习
    created_case = Column(Boolean, default=False)
    case_id = Column(Integer, ForeignKey("diagnostic_cases.id"))

    # Relationships
    datasource = relationship("Datasource", back_populates="anomalies")
    case = relationship("DiagnosticCase", back_populates="anomalies")

    def __repr__(self):
        return f"<Anomaly(id={self.id}, datasource_id={self.datasource_id}, type={self.anomaly_type}, severity={self.severity})>"
