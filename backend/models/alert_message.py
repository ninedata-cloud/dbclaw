from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base


class AlertMessage(Base):
    __tablename__ = "alert_messages"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id"), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)  # threshold_violation, custom_expression, system_error
    severity = Column(String(20), nullable=False, index=True)  # critical, high, medium, low
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    metric_name = Column(String(100), nullable=True)
    metric_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    trigger_reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)  # active, acknowledged, resolved
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
