from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from math import ceil, isfinite
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.datasource import Datasource
from backend.models.host import Host
from backend.models.host_metric import HostMetric
from backend.models.datasource_metric import DatasourceMetric
from backend.models.soft_delete import alive_filter
from backend.utils.datetime_helper import normalize_local_datetime, now


DEFAULT_MAX_POINTS = 96
MAX_MAX_POINTS = 240
DEFAULT_LOOKBACK_HOURS = 24
MAX_LOOKBACK_DAYS = 90
DEFAULT_MAX_METRICS = 12
MAX_METRICS = 20

AGGREGATION_PRESETS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
}

AUTO_BUCKET_CHOICES = [
    60,
    300,
    900,
    1800,
    3600,
    7200,
    14400,
    21600,
    43200,
    86400,
]

PREFERRED_DATASOURCE_METRICS = [
    "cpu_usage",
    "memory_usage",
    "disk_usage",
    "qps",
    "tps",
    "iops",
    "connections_active",
    "connections_total",
    "network_in",
    "network_out",
    "cache_hit_rate",
    "throughput",
]

PREFERRED_HOST_METRICS = [
    "cpu_usage",
    "memory_usage",
    "disk_usage",
    "load_avg_1min",
    "load_avg_5min",
    "load_avg_15min",
    "host_network_rx_bytes",
    "host_network_tx_bytes",
    "total_memory_mb",
]


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return isfinite(float(value))


def _coerce_metric_dict(payload: Mapping[str, Any] | None) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, value in (payload or {}).items():
        if _is_numeric(value):
            metrics[str(key)] = round(float(value), 6)
    return metrics


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return normalize_local_datetime(value)

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        raise ValueError(
            "时间格式无效，请使用 ISO 8601 或 YYYY-MM-DD HH:MM[:SS] 格式"
        )

    return normalize_local_datetime(parsed)


def resolve_time_range(
    start_time: Any = None,
    end_time: Any = None,
    *,
    default_lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    max_lookback_days: int = MAX_LOOKBACK_DAYS,
) -> tuple[datetime, datetime]:
    end_dt = _parse_datetime(end_time) or now()
    start_dt = _parse_datetime(start_time) or (end_dt - timedelta(hours=default_lookback_hours))

    if start_dt > end_dt:
        raise ValueError("start_time 不能晚于 end_time")

    if end_dt - start_dt > timedelta(days=max_lookback_days):
        raise ValueError(f"时间范围过大，最长支持 {max_lookback_days} 天")

    return start_dt, end_dt


def resolve_bucket_seconds(
    start_time: datetime,
    end_time: datetime,
    *,
    aggregate: str = "auto",
    max_points: int = DEFAULT_MAX_POINTS,
) -> int:
    max_points = max(1, min(int(max_points or DEFAULT_MAX_POINTS), MAX_MAX_POINTS))
    if aggregate != "auto":
        if aggregate not in AGGREGATION_PRESETS:
            raise ValueError(
                "aggregate 仅支持 auto, "
                + ", ".join(["auto"] + list(AGGREGATION_PRESETS.keys()))
            )
        return AGGREGATION_PRESETS[aggregate]

    total_seconds = max(1, int((end_time - start_time).total_seconds()))
    ideal_bucket = max(1, ceil(total_seconds / max_points))
    for choice in AUTO_BUCKET_CHOICES:
        if choice >= ideal_bucket:
            return choice
    return AUTO_BUCKET_CHOICES[-1]


def _bucket_label(bucket_seconds: int) -> str:
    for label, seconds in AGGREGATION_PRESETS.items():
        if seconds == bucket_seconds:
            return label
    if bucket_seconds % 86400 == 0:
        return f"{bucket_seconds // 86400}d"
    if bucket_seconds % 3600 == 0:
        return f"{bucket_seconds // 3600}h"
    if bucket_seconds % 60 == 0:
        return f"{bucket_seconds // 60}m"
    return f"{bucket_seconds}s"


def _align_bucket_start(ts: datetime, bucket_seconds: int) -> datetime:
    aligned_epoch = int(ts.timestamp()) // bucket_seconds * bucket_seconds
    return datetime.fromtimestamp(aligned_epoch)


def select_metric_names(
    records: Sequence[tuple[datetime, Mapping[str, Any]]],
    *,
    requested_metric_names: Sequence[str] | None = None,
    preferred_metric_names: Sequence[str] | None = None,
    max_metrics: int = DEFAULT_MAX_METRICS,
) -> tuple[list[str], list[str]]:
    available_counter: Counter[str] = Counter()
    for _, payload in records:
        available_counter.update(_coerce_metric_dict(payload).keys())

    available = sorted(available_counter.keys())
    if not available:
        return [], []

    requested = [str(item).strip() for item in (requested_metric_names or []) if str(item).strip()]
    if requested:
        selected = [name for name in requested if name in available_counter]
        return selected[:MAX_METRICS], available

    preferred = [name for name in (preferred_metric_names or []) if name in available_counter]
    remaining = [
        name
        for name, _ in sorted(available_counter.items(), key=lambda item: (-item[1], item[0]))
        if name not in preferred
    ]
    limit = max(1, min(int(max_metrics or DEFAULT_MAX_METRICS), MAX_METRICS))
    return (preferred + remaining)[:limit], available


def aggregate_metric_records(
    records: Sequence[tuple[datetime, Mapping[str, Any]]],
    *,
    metric_names: Sequence[str],
    bucket_seconds: int,
) -> dict[str, Any]:
    selected_names = [str(name) for name in metric_names if str(name).strip()]
    if not selected_names:
        return {
            "selected_metric_names": [],
            "returned_metric_names": [],
            "series": {},
            "summary": {},
            "raw_point_count": len(records),
            "bucket_count": 0,
        }

    bucket_map: dict[datetime, dict[str, dict[str, Any]]] = defaultdict(dict)
    overall_map: dict[str, dict[str, Any]] = {}

    for collected_at, payload in records:
        values = _coerce_metric_dict(payload)
        if not values:
            continue

        bucket_start = _align_bucket_start(collected_at, bucket_seconds)
        for metric_name in selected_names:
            if metric_name not in values:
                continue

            value = values[metric_name]
            bucket_stat = bucket_map[bucket_start].get(metric_name)
            if bucket_stat is None:
                bucket_stat = {
                    "count": 0,
                    "sum": 0.0,
                    "min": value,
                    "max": value,
                    "last": value,
                    "last_at": collected_at,
                }
                bucket_map[bucket_start][metric_name] = bucket_stat

            bucket_stat["count"] += 1
            bucket_stat["sum"] += value
            bucket_stat["min"] = min(bucket_stat["min"], value)
            bucket_stat["max"] = max(bucket_stat["max"], value)
            if collected_at >= bucket_stat["last_at"]:
                bucket_stat["last"] = value
                bucket_stat["last_at"] = collected_at

            overall_stat = overall_map.get(metric_name)
            if overall_stat is None:
                overall_stat = {
                    "count": 0,
                    "sum": 0.0,
                    "min": value,
                    "max": value,
                    "last": value,
                    "last_at": collected_at,
                    "first_at": collected_at,
                }
                overall_map[metric_name] = overall_stat

            overall_stat["count"] += 1
            overall_stat["sum"] += value
            overall_stat["min"] = min(overall_stat["min"], value)
            overall_stat["max"] = max(overall_stat["max"], value)
            if collected_at >= overall_stat["last_at"]:
                overall_stat["last"] = value
                overall_stat["last_at"] = collected_at
            if collected_at <= overall_stat["first_at"]:
                overall_stat["first_at"] = collected_at

    series: dict[str, list[dict[str, Any]]] = {name: [] for name in selected_names}
    for bucket_start in sorted(bucket_map.keys()):
        for metric_name in selected_names:
            stat = bucket_map[bucket_start].get(metric_name)
            if not stat:
                continue
            count = stat["count"]
            series[metric_name].append(
                {
                    "bucket_start": bucket_start.isoformat(),
                    "bucket_end": (bucket_start + timedelta(seconds=bucket_seconds)).isoformat(),
                    "avg": round(stat["sum"] / count, 4),
                    "min": round(stat["min"], 4),
                    "max": round(stat["max"], 4),
                    "last": round(stat["last"], 4),
                    "count": count,
                }
            )

    summary: dict[str, dict[str, Any]] = {}
    for metric_name in selected_names:
        stat = overall_map.get(metric_name)
        if not stat:
            continue
        summary[metric_name] = {
            "avg": round(stat["sum"] / stat["count"], 4),
            "min": round(stat["min"], 4),
            "max": round(stat["max"], 4),
            "last": round(stat["last"], 4),
            "count": stat["count"],
            "first_at": stat["first_at"].isoformat(),
            "last_at": stat["last_at"].isoformat(),
        }

    non_empty_series = {name: points for name, points in series.items() if points}
    return {
        "selected_metric_names": [name for name in selected_names if name in non_empty_series],
        "returned_metric_names": sorted(overall_map.keys()),
        "series": non_empty_series,
        "summary": summary,
        "raw_point_count": len(records),
        "bucket_count": len(bucket_map),
    }


async def _get_datasource_or_raise(db: AsyncSession, datasource_id: int) -> Datasource:
    result = await db.execute(
        select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
    )
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise ValueError(f"数据源 {datasource_id} 不存在")
    return datasource


async def _get_host(db: AsyncSession, host_id: int | None) -> Host | None:
    if not host_id:
        return None
    result = await db.execute(select(Host).where(Host.id == host_id, alive_filter(Host)))
    return result.scalar_one_or_none()


async def _load_datasource_records(
    db: AsyncSession,
    *,
    datasource_id: int,
    metric_type: str,
    start_time: datetime,
    end_time: datetime,
) -> list[tuple[datetime, dict[str, float]]]:
    result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == datasource_id,
            DatasourceMetric.metric_type == metric_type,
            DatasourceMetric.collected_at >= start_time,
            DatasourceMetric.collected_at <= end_time,
        )
        .order_by(DatasourceMetric.collected_at.asc())
    )
    snapshots = result.scalars().all()
    return [(snapshot.collected_at, _coerce_metric_dict(snapshot.data or {})) for snapshot in snapshots]


async def _load_host_records(
    db: AsyncSession,
    *,
    host_id: int,
    start_time: datetime,
    end_time: datetime,
) -> list[tuple[datetime, dict[str, float]]]:
    result = await db.execute(
        select(HostMetric)
        .where(
            HostMetric.host_id == host_id,
            HostMetric.collected_at >= start_time,
            HostMetric.collected_at <= end_time,
        )
        .order_by(HostMetric.collected_at.asc())
    )
    metrics = result.scalars().all()

    records: list[tuple[datetime, dict[str, float]]] = []
    for metric in metrics:
        payload = _coerce_metric_dict(metric.data or {})
        for field_name in ("cpu_usage", "memory_usage", "disk_usage"):
            value = getattr(metric, field_name, None)
            if _is_numeric(value):
                payload[field_name] = round(float(value), 6)
        records.append((metric.collected_at, payload))
    return records


async def query_monitoring_history(
    db: AsyncSession,
    *,
    datasource_id: int,
    start_time: Any = None,
    end_time: Any = None,
    scope: str = "both",
    metric_type: str = "db_status",
    metric_names: Sequence[str] | None = None,
    aggregate: str = "auto",
    max_points: int = DEFAULT_MAX_POINTS,
    max_metrics: int = DEFAULT_MAX_METRICS,
) -> dict[str, Any]:
    scope = str(scope or "both").strip().lower()
    if scope not in {"datasource", "host", "both"}:
        raise ValueError("scope 仅支持 datasource、host、both")

    datasource = await _get_datasource_or_raise(db, datasource_id)
    host = await _get_host(db, datasource.host_id)
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    bucket_seconds = resolve_bucket_seconds(
        start_dt,
        end_dt,
        aggregate=str(aggregate or "auto").strip().lower(),
        max_points=int(max_points or DEFAULT_MAX_POINTS),
    )

    result: dict[str, Any] = {
        "success": True,
        "scope": scope,
        "datasource": {
            "id": datasource.id,
            "name": datasource.name,
            "db_type": datasource.db_type,
            "host_id": datasource.host_id,
            "metric_source": datasource.metric_source,
        },
        "time_range": {
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
        },
        "aggregation": {
            "mode": "auto" if str(aggregate or "auto").strip().lower() == "auto" else str(aggregate).strip().lower(),
            "bucket_seconds": bucket_seconds,
            "bucket_label": _bucket_label(bucket_seconds),
            "max_points": max(1, min(int(max_points or DEFAULT_MAX_POINTS), MAX_MAX_POINTS)),
        },
        "requested_metric_names": [str(name).strip() for name in (metric_names or []) if str(name).strip()],
    }

    if scope in {"datasource", "both"}:
        datasource_records = await _load_datasource_records(
            db,
            datasource_id=datasource.id,
            metric_type=metric_type,
            start_time=start_dt,
            end_time=end_dt,
        )
        selected_metrics, available_metrics = select_metric_names(
            datasource_records,
            requested_metric_names=metric_names,
            preferred_metric_names=PREFERRED_DATASOURCE_METRICS,
            max_metrics=max_metrics,
        )
        aggregated = aggregate_metric_records(
            datasource_records,
            metric_names=selected_metrics,
            bucket_seconds=bucket_seconds,
        )
        result["datasource_metric"] = {
            "metric_type": metric_type,
            "available_metric_names": available_metrics,
            **aggregated,
        }

    if scope in {"host", "both"}:
        if not host:
            host_payload = {
                "available": False,
                "reason": "当前数据源未关联主机，无法查询主机监控历史",
            }
            if scope == "host":
                return {"success": False, "error": host_payload["reason"], **result, "host_metric": host_payload}
            result["host_metric"] = host_payload
        else:
            host_records = await _load_host_records(
                db,
                host_id=host.id,
                start_time=start_dt,
                end_time=end_dt,
            )
            selected_metrics, available_metrics = select_metric_names(
                host_records,
                requested_metric_names=metric_names,
                preferred_metric_names=PREFERRED_HOST_METRICS,
                max_metrics=max_metrics,
            )
            aggregated = aggregate_metric_records(
                host_records,
                metric_names=selected_metrics,
                bucket_seconds=bucket_seconds,
            )
            result["host"] = {
                "id": host.id,
                "name": host.name,
                "host": host.host,
                "os_version": host.os_version,
            }
            result["host_metric"] = {
                "available": True,
                "available_metric_names": available_metrics,
                **aggregated,
            }

    return result
