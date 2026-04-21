from sqlalchemy import Column, Integer, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class AlertSubscription(SoftDeleteMixin, Base):
    __tablename__ = "alert_subscription"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    datasource_ids = Column(JSON, nullable=False, default=list)  # empty = all datasource
    severity_levels = Column(JSON, nullable=False, default=list)  # empty = all severities
    time_ranges = Column(JSON, nullable=False, default=list)  # empty = 24/7
    integration_targets = Column(JSON, nullable=False, default=list)
    is_enabled = Column("is_enabled", Boolean, nullable=False, default=True, index=True)
    aggregation_script = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    enabled = synonym("is_enabled")
