"""
Alert Event Model

Represents aggregated alert events that group related alerts together.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from datetime import datetime

from backend.database import Base


class AlertEvent(Base):
    """Alert Event model for aggregated alerts"""

    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    aggregation_key = Column(String(255), nullable=False, index=True)
    aggregation_type = Column(String(50), nullable=False)

    # Event metadata
    first_alert_id = Column(Integer, nullable=False)
    latest_alert_id = Column(Integer, nullable=False)
    alert_count = Column(Integer, nullable=False, default=1)

    # Time tracking
    event_start_time = Column(DateTime, nullable=False, index=True)
    event_end_time = Column(DateTime, nullable=False, index=True)
    last_updated = Column(DateTime, nullable=False, default=datetime.now)

    # Status (inherited from latest alert)
    status = Column(String(20), nullable=False, index=True)
    severity = Column(String(20), nullable=False)

    # Display metadata
    title = Column(String(255), nullable=False)
    alert_type = Column(String(50), nullable=True)
    metric_name = Column(String(100), nullable=True)
    event_category = Column(String(50), nullable=True, index=True)
    fault_domain = Column(String(50), nullable=True, index=True)
    lifecycle_stage = Column(String(30), nullable=True, index=True)
    diagnosis_refresh_needed = Column(Boolean, nullable=False, default=True)
    diagnosis_trigger_reason = Column(String(50), nullable=True, index=True)
    last_diagnosed_severity = Column(String(20), nullable=True)
    last_diagnosed_alert_count = Column(Integer, nullable=True)
    last_diagnosis_requested_at = Column(DateTime, nullable=True, index=True)
    ai_diagnosis_summary = Column(Text, nullable=True)  # AI-generated diagnosis for this event
    root_cause = Column(Text, nullable=True)            # Root cause analysis
    recommended_actions = Column(Text, nullable=True)  # Recommended fix actions
    diagnosis_status = Column(String(20), nullable=True)  # pending / in_progress / completed / failed
    diagnosis_started_at = Column(DateTime, nullable=True, index=True)
    diagnosis_completed_at = Column(DateTime, nullable=True, index=True)
    diagnosis_source_event_id = Column(Integer, nullable=True, index=True)

    def __repr__(self):
        return (
            f"<AlertEvent(id={self.id}, key={self.aggregation_key}, "
            f"count={self.alert_count}, status={self.status})>"
        )
