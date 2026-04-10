from sqlalchemy import Column, Integer, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class AlertSubscription(SoftDeleteMixin, Base):
    __tablename__ = "alert_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    datasource_ids = Column(JSON, nullable=False, default=list)  # empty = all datasources
    severity_levels = Column(JSON, nullable=False, default=list)  # empty = all severities
    time_ranges = Column(JSON, nullable=False, default=list)  # empty = 24/7
    integration_targets = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    aggregation_script = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
