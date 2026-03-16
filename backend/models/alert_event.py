"""
Alert Event Model

Represents aggregated alert events that group related alerts together.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from backend.database import Base


class AlertEvent(Base):
    """Alert Event model for aggregated alerts"""

    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id"), nullable=False, index=True)
    aggregation_key = Column(String(255), nullable=False, index=True)
    aggregation_type = Column(String(50), nullable=False)

    # Event metadata
    first_alert_id = Column(Integer, ForeignKey("alert_messages.id"), nullable=False)
    latest_alert_id = Column(Integer, ForeignKey("alert_messages.id"), nullable=False)
    alert_count = Column(Integer, nullable=False, default=1)

    # Time tracking
    event_start_time = Column(DateTime, nullable=False, index=True)
    event_end_time = Column(DateTime, nullable=False, index=True)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Status (inherited from latest alert)
    status = Column(String(20), nullable=False, index=True)
    severity = Column(String(20), nullable=False)

    # Display metadata
    title = Column(String(255), nullable=False)
    alert_type = Column(String(50), nullable=True)
    metric_name = Column(String(100), nullable=True)

    # Relationships
    datasource = relationship("Datasource", back_populates="alert_events")
    alerts = relationship(
        "AlertMessage",
        foreign_keys="AlertMessage.event_id",
        back_populates="event",
        lazy="selectin"
    )
    first_alert = relationship(
        "AlertMessage",
        foreign_keys=[first_alert_id],
        lazy="selectin"
    )
    latest_alert = relationship(
        "AlertMessage",
        foreign_keys=[latest_alert_id],
        lazy="selectin"
    )

    def __repr__(self):
        return (
            f"<AlertEvent(id={self.id}, key={self.aggregation_key}, "
            f"count={self.alert_count}, status={self.status})>"
        )
