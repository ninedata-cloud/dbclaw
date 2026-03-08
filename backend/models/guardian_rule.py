"""
Guardian Rule Models
自然语言规则模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text, LargeBinary
from sqlalchemy.orm import relationship
from backend.database import Base


class GuardianRule(Base):
    """自然语言规则表"""
    __tablename__ = "guardian_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200))
    description_nl = Column(Text)  # 自然语言描述
    rule_embedding = Column(LargeBinary)  # 向量嵌入（用于语义匹配）

    # 解析后的结构
    conditions = Column(JSON)  # AI 解析的条件
    actions = Column(JSON)     # AI 解析的动作
    scope = Column(JSON)       # 适用范围

    # 学习指标
    effectiveness_score = Column(Float, default=0.5)  # 有效性评分
    false_positive_rate = Column(Float, default=0.0)
    execution_count = Column(Integer, default=0)
    last_triggered = Column(DateTime)

    # 对话元数据
    created_by_dialogue = Column(Boolean, default=False)
    training_conversation_id = Column(Integer, ForeignKey("diagnostic_sessions.id"))
    refinement_history = Column(JSON)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    training_conversation = relationship("DiagnosticSession", back_populates="trained_rules")
    executions = relationship("RuleExecution", back_populates="rule")

    def __repr__(self):
        return f"<GuardianRule(id={self.id}, name={self.name}, active={self.is_active})>"


class RuleExecution(Base):
    """规则执行日志"""
    __tablename__ = "rule_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("guardian_rules.id"), nullable=False)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False)
    executed_at = Column(DateTime, default=datetime.utcnow)

    # 上下文
    trigger_context = Column(JSON)
    conditions_met = Column(JSON)

    # 执行
    actions_executed = Column(JSON)
    required_approval = Column(Boolean, default=False)
    approved_by = Column(Integer, ForeignKey("users.id"))

    # 结果
    success = Column(Boolean)
    error_message = Column(Text)
    execution_time_ms = Column(Integer)

    # 反馈
    was_helpful = Column(Boolean)
    user_feedback = Column(Text)

    # Relationships
    rule = relationship("GuardianRule", back_populates="executions")
    datasource = relationship("Datasource")
    approver = relationship("User")

    def __repr__(self):
        return f"<RuleExecution(id={self.id}, rule_id={self.rule_id}, success={self.success})>"
