from sqlalchemy import Column, Integer, String, DateTime, Float, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class MetricBaselineProfile(Base):
    __tablename__ = "metric_baseline_profiles"
    __table_args__ = (
        UniqueConstraint(
            "datasource_id",
            "metric_name",
            "weekday",
            "hour",
            name="uq_metric_baseline_profile_slot",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    metric_name = Column(String(100), nullable=False, index=True)
    weekday = Column(Integer, nullable=False, index=True)
    hour = Column(Integer, nullable=False, index=True)
    sample_count = Column(Integer, nullable=False, default=0)
    avg_value = Column(Float, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    p50_value = Column(Float, nullable=True)
    p95_value = Column(Float, nullable=True)
    stddev_value = Column(Float, nullable=True)
    last_snapshot_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
