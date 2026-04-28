"""User-managed scheduled Python task models."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class ScheduledTask(SoftDeleteMixin, Base):
    """Persisted task definition registered with the runtime scheduler."""

    __tablename__ = "scheduled_task"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    script_code = Column(Text, nullable=False)
    schedule_type = Column(String(20), nullable=False, index=True)  # interval / cron
    schedule_config = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    timeout_seconds = Column(Integer, nullable=False, default=60)
    max_concurrent_runs = Column(Integer, nullable=False, default=1)
    notification_policy = Column(String(20), nullable=False, default="never")
    notification_targets = Column(JSON, nullable=False, default=list)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(20), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("app_user.id"), nullable=True, index=True)
    updated_by_id = Column(Integer, ForeignKey("app_user.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    runs = relationship("ScheduledTaskRun", back_populates="task", cascade="all, delete-orphan")


class ScheduledTaskRun(Base):
    """One execution attempt for a scheduled task."""

    __tablename__ = "scheduled_task_run"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    task_id = Column(Integer, ForeignKey("scheduled_task.id"), nullable=False, index=True)
    trigger_source = Column(String(50), nullable=False, default="manual", index=True)  # manual / scheduler
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending/running/success/failed/skipped
    started_at = Column(DateTime(timezone=True), nullable=True, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    result = Column(JSON, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    task = relationship("ScheduledTask", back_populates="runs")
