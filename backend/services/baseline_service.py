"""
Per-datasource metric baseline profiles and deterministic baseline alerting.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.metric_baseline_profile import MetricBaselineProfile
from backend.models.datasource_metric import DatasourceMetric
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

DEFAULT_BASELINE_CONFIG: dict[str, Any] = {
    "enabled": False,
    "learning_days": 14,
    "min_samples": 24,
    "deviation_ratio": 1.35,
    "min_absolute_delta": 10.0,
    "refresh_interval_minutes": 10,
    "metrics": {
        "cpu_usage": {"enabled": True, "duration": 300, "severity": "medium", "minimum": 20},
        "disk_usage": {"enabled": True, "duration": 600, "severity": "high", "minimum": 70},
        "connections": {"enabled": True, "duration": 300, "severity": "medium", "minimum": 10},
    },
}

METRIC_ALIASES: dict[str, list[str]] = {
    "cpu_usage": ["cpu_usage", "cpu_usage_percent", "cpu_percent"],
    "disk_usage": ["disk_usage", "disk_usage_percent", "disk_percent"],
    "connections": [
        "connections",
        "connections_active",
        "threads_running",
        "active_connections",
        "connection_count",
    ],
}


def normalize_baseline_config(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "enabled": bool(DEFAULT_BASELINE_CONFIG["enabled"]),
        "learning_days": int(DEFAULT_BASELINE_CONFIG["learning_days"]),
        "min_samples": int(DEFAULT_BASELINE_CONFIG["min_samples"]),
        "deviation_ratio": float(DEFAULT_BASELINE_CONFIG["deviation_ratio"]),
        "min_absolute_delta": float(DEFAULT_BASELINE_CONFIG["min_absolute_delta"]),
        "refresh_interval_minutes": int(DEFAULT_BASELINE_CONFIG["refresh_interval_minutes"]),
        "metrics": {
            metric_name: dict(metric_config)
            for metric_name, metric_config in DEFAULT_BASELINE_CONFIG["metrics"].items()
        },
    }
    if not isinstance(config, dict):
        return merged

    if "enabled" in config:
        merged["enabled"] = bool(config.get("enabled"))
    if config.get("learning_days") is not None:
        merged["learning_days"] = max(3, min(60, int(config.get("learning_days"))))
    if config.get("min_samples") is not None:
        merged["min_samples"] = max(6, min(500, int(config.get("min_samples"))))
    if config.get("deviation_ratio") is not None:
        merged["deviation_ratio"] = max(1.05, min(5.0, float(config.get("deviation_ratio"))))
    if config.get("min_absolute_delta") is not None:
        merged["min_absolute_delta"] = max(0.0, float(config.get("min_absolute_delta")))
    if config.get("refresh_interval_minutes") is not None:
        merged["refresh_interval_minutes"] = max(1, min(240, int(config.get("refresh_interval_minutes"))))

    metrics_config = config.get("metrics")
    if isinstance(metrics_config, dict):
        for metric_name, default_metric_config in merged["metrics"].items():
            current = metrics_config.get(metric_name)
            if not isinstance(current, dict):
                continue
            if "enabled" in current:
                default_metric_config["enabled"] = bool(current.get("enabled"))
            if current.get("duration") is not None:
                default_metric_config["duration"] = max(60, int(current.get("duration")))
            severity = str(current.get("severity") or default_metric_config.get("severity") or "medium").strip().lower()
            default_metric_config["severity"] = severity if severity in {"critical", "high", "medium", "low"} else "medium"
            if current.get("minimum") is not None:
                default_metric_config["minimum"] = float(current.get("minimum"))

    return merged


def extract_metric_value(metrics: dict[str, Any], metric_name: str) -> Optional[float]:
    aliases = METRIC_ALIASES.get(metric_name, [metric_name])
    for key in aliases:
        value = metrics.get(key)
        try:
            if value is None:
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _percentile(values: list[float], ratio: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[int(position)])
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    return float(lower_value + (upper_value - lower_value) * (position - lower))


def build_profile_stats(values: list[float]) -> dict[str, Optional[float]]:
    if not values:
        return {
            "sample_count": 0,
            "avg_value": None,
            "min_value": None,
            "max_value": None,
            "p50_value": None,
            "p95_value": None,
            "stddev_value": None,
        }

    count = len(values)
    avg_value = sum(values) / count
    variance = sum((value - avg_value) ** 2 for value in values) / count if count > 1 else 0.0
    return {
        "sample_count": count,
        "avg_value": round(avg_value, 4),
        "min_value": round(min(values), 4),
        "max_value": round(max(values), 4),
        "p50_value": round(_percentile(values, 0.5) or 0.0, 4),
        "p95_value": round(_percentile(values, 0.95) or 0.0, 4),
        "stddev_value": round(math.sqrt(max(variance, 0.0)), 4),
    }


def compute_upper_bound(profile: MetricBaselineProfile | dict[str, Any], baseline_config: dict[str, Any]) -> Optional[float]:
    p95_value = getattr(profile, "p95_value", None) if not isinstance(profile, dict) else profile.get("p95_value")
    avg_value = getattr(profile, "avg_value", None) if not isinstance(profile, dict) else profile.get("avg_value")
    if p95_value is None and avg_value is None:
        return None

    base_value = float(p95_value if p95_value is not None else avg_value)
    ratio = float(baseline_config.get("deviation_ratio") or DEFAULT_BASELINE_CONFIG["deviation_ratio"])
    absolute = float(baseline_config.get("min_absolute_delta") or DEFAULT_BASELINE_CONFIG["min_absolute_delta"])
    return round(max(base_value * ratio, base_value + absolute), 4)


class BaselineSignalDetector:
    def __init__(self):
        self._violation_start_times: dict[int, dict[str, datetime]] = defaultdict(dict)
        self._last_trigger_times: dict[int, dict[str, datetime]] = defaultdict(dict)
        self._violation_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._trigger_cooldown = 3600

    def check_baselines(
        self,
        datasource_id: int,
        metrics: dict[str, Any],
        profiles_by_metric: dict[str, MetricBaselineProfile],
        baseline_config: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        config = normalize_baseline_config(baseline_config)
        if not config.get("enabled"):
            return []

        current_time = now()
        violations: list[dict[str, Any]] = []
        min_samples = int(config["min_samples"])

        for metric_name, metric_config in config["metrics"].items():
            if not metric_config.get("enabled", False):
                continue

            profile = profiles_by_metric.get(metric_name)
            if not profile or int(profile.sample_count or 0) < min_samples:
                continue

            current_value = extract_metric_value(metrics, metric_name)
            if current_value is None:
                self._clear_metric_state(datasource_id, metric_name)
                continue

            upper_bound = compute_upper_bound(profile, config)
            minimum = metric_config.get("minimum")
            if minimum is not None:
                upper_bound = max(float(upper_bound or 0.0), float(minimum))
            if upper_bound is None:
                continue

            is_violated = current_value > upper_bound
            if is_violated:
                if metric_name not in self._violation_start_times[datasource_id]:
                    self._violation_start_times[datasource_id][metric_name] = current_time

                violation_duration = (current_time - self._violation_start_times[datasource_id][metric_name]).total_seconds()
                required_duration = max(60, int(metric_config.get("duration") or 300))
                if violation_duration < required_duration:
                    continue

                last_trigger = self._last_trigger_times[datasource_id].get(metric_name)
                if last_trigger and (current_time - last_trigger).total_seconds() < self._trigger_cooldown:
                    continue

                required_confirmations = max(1, int(metric_config.get("confirmations") or 2))
                self._violation_counts[datasource_id][metric_name] += 1
                if self._violation_counts[datasource_id][metric_name] < required_confirmations:
                    continue

                self._violation_counts[datasource_id][metric_name] = 0
                self._last_trigger_times[datasource_id][metric_name] = current_time
                violations.append(
                    {
                        "metric_name": metric_name,
                        "current_value": round(current_value, 4),
                        "baseline_avg": profile.avg_value,
                        "baseline_p95": profile.p95_value,
                        "upper_bound": upper_bound,
                        "duration": required_duration,
                        "violation_duration": violation_duration,
                        "sample_count": int(profile.sample_count or 0),
                        "severity": metric_config.get("severity") or "medium",
                        "slot_label": f"周{profile.weekday + 1} {int(profile.hour):02d}:00",
                    }
                )
            else:
                self._clear_metric_state(datasource_id, metric_name)

        return violations

    def _clear_metric_state(self, datasource_id: int, metric_name: str) -> None:
        self._violation_start_times[datasource_id].pop(metric_name, None)
        self._last_trigger_times[datasource_id].pop(metric_name, None)
        self._violation_counts[datasource_id].pop(metric_name, None)


async def get_profiles_for_slot(
    db: AsyncSession,
    datasource_id: int,
    collected_at: datetime,
    metric_names: list[str],
) -> dict[str, MetricBaselineProfile]:
    if not metric_names:
        return {}
    result = await db.execute(
        select(MetricBaselineProfile).where(
            MetricBaselineProfile.datasource_id == datasource_id,
            MetricBaselineProfile.weekday == collected_at.weekday(),
            MetricBaselineProfile.hour == collected_at.hour,
            MetricBaselineProfile.metric_name.in_(metric_names),
        )
    )
    return {item.metric_name: item for item in result.scalars().all()}


async def refresh_current_slot_profiles(
    db: AsyncSession,
    datasource_id: int,
    collected_at: datetime,
    baseline_config: Optional[dict[str, Any]],
) -> dict[str, MetricBaselineProfile]:
    config = normalize_baseline_config(baseline_config)
    enabled_metrics = [name for name, metric_config in config["metrics"].items() if metric_config.get("enabled")]
    profiles = await get_profiles_for_slot(db, datasource_id, collected_at, enabled_metrics)
    if not config.get("enabled") or not enabled_metrics:
        return profiles

    refresh_cutoff = collected_at - timedelta(minutes=int(config["refresh_interval_minutes"]))
    if profiles and all(profile.updated_at and profile.updated_at >= refresh_cutoff for profile in profiles.values()) and len(profiles) == len(enabled_metrics):
        return profiles

    await rebuild_baseline_profiles_for_datasource(
        db,
        datasource_id=datasource_id,
        baseline_config=config,
        metric_names=enabled_metrics,
        target_slots={(collected_at.weekday(), collected_at.hour)},
    )
    return await get_profiles_for_slot(db, datasource_id, collected_at, enabled_metrics)


async def rebuild_baseline_profiles_for_datasource(
    db: AsyncSession,
    datasource_id: int,
    baseline_config: Optional[dict[str, Any]],
    *,
    metric_names: Optional[list[str]] = None,
    target_slots: Optional[set[tuple[int, int]]] = None,
) -> dict[str, Any]:
    config = normalize_baseline_config(baseline_config)
    enabled_metrics = metric_names or [name for name, metric_config in config["metrics"].items() if metric_config.get("enabled")]
    if not config.get("enabled") or not enabled_metrics:
        return {"profiles_upserted": 0, "snapshots_scanned": 0, "metric_names": enabled_metrics}

    cutoff = now() - timedelta(days=int(config["learning_days"]))
    result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == datasource_id,
            DatasourceMetric.metric_type == "db_status",
            DatasourceMetric.collected_at >= cutoff,
        )
        .order_by(DatasourceMetric.collected_at.asc())
    )
    snapshots = result.scalars().all()

    grouped_values: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    last_snapshot_at: dict[tuple[str, int, int], datetime] = {}
    for snapshot in snapshots:
        slot = (snapshot.collected_at.weekday(), snapshot.collected_at.hour)
        if target_slots and slot not in target_slots:
            continue
        data = snapshot.data if isinstance(snapshot.data, dict) else {}
        for metric_name in enabled_metrics:
            value = extract_metric_value(data, metric_name)
            if value is None:
                continue
            key = (metric_name, slot[0], slot[1])
            grouped_values[key].append(value)
            last_snapshot_at[key] = snapshot.collected_at

    if target_slots:
        for weekday, hour in target_slots:
            await db.execute(
                delete(MetricBaselineProfile).where(
                    MetricBaselineProfile.datasource_id == datasource_id,
                    MetricBaselineProfile.weekday == weekday,
                    MetricBaselineProfile.hour == hour,
                    MetricBaselineProfile.metric_name.in_(enabled_metrics),
                )
            )

    existing_result = await db.execute(
        select(MetricBaselineProfile).where(
            MetricBaselineProfile.datasource_id == datasource_id,
            MetricBaselineProfile.metric_name.in_(enabled_metrics),
        )
    )
    existing = {
        (item.metric_name, item.weekday, item.hour): item
        for item in existing_result.scalars().all()
    }

    profiles_upserted = 0
    for key, values in grouped_values.items():
        metric_name, weekday, hour = key
        stats = build_profile_stats(values)
        profile = existing.get(key)
        if profile is None:
            profile = MetricBaselineProfile(
                datasource_id=datasource_id,
                metric_name=metric_name,
                weekday=weekday,
                hour=hour,
            )
            db.add(profile)

        profile.sample_count = stats["sample_count"] or 0
        profile.avg_value = stats["avg_value"]
        profile.min_value = stats["min_value"]
        profile.max_value = stats["max_value"]
        profile.p50_value = stats["p50_value"]
        profile.p95_value = stats["p95_value"]
        profile.stddev_value = stats["stddev_value"]
        profile.last_snapshot_at = last_snapshot_at.get(key)
        profile.updated_at = now()
        profiles_upserted += 1

    await db.commit()
    return {
        "profiles_upserted": profiles_upserted,
        "snapshots_scanned": len(snapshots),
        "metric_names": enabled_metrics,
    }


async def list_baseline_profiles_for_datasource(
    db: AsyncSession,
    datasource_id: int,
    *,
    limit: Optional[int] = None,
) -> list[MetricBaselineProfile]:
    stmt = (
        select(MetricBaselineProfile)
        .where(MetricBaselineProfile.datasource_id == datasource_id)
        .order_by(MetricBaselineProfile.metric_name.asc(), MetricBaselineProfile.weekday.asc(), MetricBaselineProfile.hour.asc())
    )
    if limit is not None:
        stmt = stmt.limit(max(1, int(limit)))
    result = await db.execute(stmt)
    return result.scalars().all()
