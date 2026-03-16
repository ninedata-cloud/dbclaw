from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from backend.database import Base


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    datasource_ids = Column(JSON, nullable=False, default=list)  # empty = all datasources
    severity_levels = Column(JSON, nullable=False, default=list)  # empty = all severities
    time_ranges = Column(JSON, nullable=False, default=list)  # empty = 24/7
    channels = Column(JSON, nullable=False, default=list)  # ["email", "sms", "phone", "webhook"]
    webhook_url = Column(String(500), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    aggregation_script = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
