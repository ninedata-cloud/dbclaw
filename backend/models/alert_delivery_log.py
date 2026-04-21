from sqlalchemy import BigInteger, Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class AlertDeliveryLog(Base):
    __tablename__ = "alert_delivery_log"

    id = Column(BigInteger, primary_key=True, index=True)
    alert_id = Column(BigInteger, nullable=False, index=True)
    subscription_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, nullable=True, index=True)
    target_id = Column(String(100), nullable=True, index=True)
    target_name = Column(String(255), nullable=True)
    channel = Column(String(100), nullable=False)  # integration:builtin_email, integration:builtin_dingtalk, etc.
    recipient = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, sent, failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
