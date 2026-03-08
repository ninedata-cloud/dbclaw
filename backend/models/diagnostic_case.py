"""
Diagnostic Case Models
诊断案例学习模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text, LargeBinary
from sqlalchemy.orm import relationship
from backend.database import Base


class DiagnosticCase(Base):
    """诊断案例表 - 学习库"""
    __tablename__ = "diagnostic_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 问题
    symptoms = Column(JSON)
    symptom_embedding = Column(LargeBinary)  # 向量嵌入
    initial_metrics = Column(JSON)

    # 诊断
    root_cause = Column(Text)
    diagnosis_steps = Column(JSON)
    diagnostic_conversation_id = Column(Integer, ForeignKey("diagnostic_sessions.id"))

    # 解决方案
    actions_taken = Column(JSON)
    effectiveness = Column(Float)  # 0-1，用户反馈
    resolution_time = Column(Integer)  # 秒

    # 学习
    reusable_solution = Column(Boolean, default=False)
    solution_template_id = Column(Integer)
    times_reused = Column(Integer, default=0)

    # 元数据
    tags = Column(JSON)
    user_rating = Column(Integer)  # 1-5
    user_feedback = Column(Text)

    # Relationships
    datasource = relationship("Datasource", back_populates="diagnostic_cases")
    diagnostic_conversation = relationship("DiagnosticSession", back_populates="cases")
    anomalies = relationship("Anomaly", back_populates="case")

    def __repr__(self):
        return f"<DiagnosticCase(id={self.id}, datasource_id={self.datasource_id}, reusable={self.reusable_solution})>"


class GuardianAlert(Base):
    """主动告警表"""
    __tablename__ = "guardian_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False)
    anomaly_id = Column(Integer, ForeignKey("anomalies.id"))
    rule_id = Column(Integer, ForeignKey("guardian_rules.id"))

    created_at = Column(DateTime, default=datetime.utcnow)
    severity = Column(String(20))
    title = Column(String(200))
    message = Column(Text)

    # 路由
    channels = Column(JSON)  # ['push', 'chat', 'sms', 'email']
    sent_at = Column(DateTime)

    # 用户交互
    status = Column(String(20), default='pending')  # pending, acknowledged, resolved, ignored
    acknowledged_at = Column(DateTime)
    user_action = Column(String(50))

    # AI 会话
    created_chat_session = Column(Boolean, default=False)
    chat_session_id = Column(Integer, ForeignKey("diagnostic_sessions.id"))

    # Relationships
    datasource = relationship("Datasource")
    anomaly = relationship("Anomaly")

    def __repr__(self):
        return f"<GuardianAlert(id={self.id}, severity={self.severity}, status={self.status})>"
