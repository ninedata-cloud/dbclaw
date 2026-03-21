from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class AlertDeliveryLog(Base):
    __tablename__ = "alert_delivery_log"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, nullable=False, index=True)
    subscription_id = Column(Integer, nullable=False, index=True)
    channel = Column(String(100), nullable=False)  # integration:builtin_email, integration:builtin_dingtalk, etc.
    recipient = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, sent, failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
