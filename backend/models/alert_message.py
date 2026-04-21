from sqlalchemy import BigInteger, Column, Integer, String, Numeric, Text, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class AlertMessage(Base):
    __tablename__ = "alert_message"

    id = Column(BigInteger, primary_key=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)  # threshold_violation, custom_expression, system_error, ai_policy_violation
    severity = Column(String(20), nullable=False, index=True)  # critical, high, medium, low
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    metric_name = Column(String(100), nullable=True)
    metric_value = Column(Numeric(22, 4), nullable=True)
    threshold_value = Column(Numeric(22, 4), nullable=True)
    trigger_reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)  # active, acknowledged, resolved
    acknowledged_by = Column(Integer, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_value = Column(Numeric(22, 4), nullable=True)  # metric value at time of recovery
    event_id = Column(Integer, nullable=True, index=True)
    notified_at = Column(DateTime(timezone=True), nullable=True, index=True)  # 首次通知完成时间，非空表示已通知
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
