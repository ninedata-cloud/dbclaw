from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.models.datasource import Datasource
from backend.utils.datetime_helper import now


SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

STATUS_ORDER = {
    "active": 0,
    "acknowledged": 1,
    "resolved": 2,
}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1]
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid datetime: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _normalize_datasource_ids(raw: Any) -> list[int]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = [item.strip() for item in str(raw).split(",") if item.strip()]
    return [int(item) for item in items]


def _normalize_bucket(bucket: str, start_time: datetime, end_time: datetime) -> tuple[str, timedelta]:
    normalized = (bucket or "auto").strip().lower()
    if normalized == "1h":
        return "1h", timedelta(hours=1)
    if normalized == "6h":
        return "6h", timedelta(hours=6)
    if normalized == "1d":
        return "1d", timedelta(days=1)

    window = end_time - start_time
    if window <= timedelta(days=2):
        return "1h", timedelta(hours=1)
    if window <= timedelta(days=14):
        return "6h", timedelta(hours=6)
    return "1d", timedelta(days=1)


def _floor_datetime(value: datetime, bucket_delta: timedelta) -> datetime:
    bucket_seconds = int(bucket_delta.total_seconds())
    epoch_seconds = int(value.timestamp())
    floored = epoch_seconds - (epoch_seconds % bucket_seconds)
    tzinfo = value.tzinfo if value.tzinfo and value.tzinfo.utcoffset(value) is not None else UTC
    return datetime.fromtimestamp(floored, tz=tzinfo)


def _counter_to_list(counter: Counter, *, top_n: int | None = None) -> list[dict[str, Any]]:
    rows = [{"value": key, "count": count} for key, count in counter.items() if key not in (None, "")]
    rows.sort(key=lambda item: (-item["count"], str(item["value"])))
    if top_n is not None:
        rows = rows[:top_n]
    return rows


async def query_alert_statistics(
    db: AsyncSession,
    *,
    scope: str = "events",
    datasource_ids: Any = None,
    start_time: Any = None,
    end_time: Any = None,
    status: str | None = "all",
    severity: str | None = None,
    bucket: str = "auto",
    top_n: int = 5,
) -> dict[str, Any]:
    normalized_scope = (scope or "events").strip().lower()
    if normalized_scope not in {"events", "alerts"}:
        return {"success": False, "error": f"unsupported scope: {scope}"}

    try:
        parsed_start = _parse_datetime(start_time)
        parsed_end = _parse_datetime(end_time)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    window_end = parsed_end or now()
    window_start = parsed_start or (window_end - timedelta(hours=24))
    if window_start > window_end:
        return {"success": False, "error": "start_time must be earlier than end_time"}

    try:
        datasource_id_list = _normalize_datasource_ids(datasource_ids)
    except ValueError:
        return {"success": False, "error": "datasource_ids must be integers"}

    top_n = max(1, min(int(top_n or 5), 20))
    bucket_label, bucket_delta = _normalize_bucket(bucket, window_start, window_end)

    datasource_result = await db.execute(select(Datasource.id, Datasource.name))
    datasource_name_map = {row.id: row.name for row in datasource_result.all()}

    if normalized_scope == "events":
        query = select(AlertEvent)
        if datasource_id_list:
            query = query.where(AlertEvent.datasource_id.in_(datasource_id_list))
        query = query.where(
            AlertEvent.event_started_at >= window_start,
            AlertEvent.event_started_at <= window_end,
        )
        if status and status != "all":
            query = query.where(AlertEvent.status == status)
        if severity:
            query = query.where(AlertEvent.severity == severity)

        result = await db.execute(query)
        records = result.scalars().all()

        severity_counter = Counter()
        status_counter = Counter()
        alert_type_counter = Counter()
        event_category_counter = Counter()
        fault_domain_counter = Counter()
        datasource_counter = Counter()
        metric_counter = Counter()
        title_counter = Counter()
        bucket_map: dict[datetime, dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "by_severity": Counter(),
                "by_status": Counter(),
            }
        )

        for record in records:
            severity_counter[record.severity] += 1
            status_counter[record.status] += 1
            alert_type_counter[record.alert_type or "unknown"] += 1
            event_category_counter[record.event_category or "unknown"] += 1
            fault_domain_counter[record.fault_domain or "unknown"] += 1
            datasource_counter[record.datasource_id] += 1
            if record.metric_name:
                metric_counter[record.metric_name] += 1
            if record.title:
                title_counter[record.title] += 1

            bucket_start = _floor_datetime(record.event_started_at, bucket_delta)
            bucket_map[bucket_start]["count"] += 1
            bucket_map[bucket_start]["by_severity"][record.severity] += 1
            bucket_map[bucket_start]["by_status"][record.status] += 1

        trend = []
        for bucket_start in sorted(bucket_map.keys()):
            data = bucket_map[bucket_start]
            trend.append(
                {
                    "bucket_start": bucket_start.isoformat(),
                    "bucket_end": (bucket_start + bucket_delta).isoformat(),
                    "count": data["count"],
                    "by_severity": dict(sorted(data["by_severity"].items(), key=lambda item: SEVERITY_ORDER.get(item[0], 99))),
                    "by_status": dict(sorted(data["by_status"].items(), key=lambda item: STATUS_ORDER.get(item[0], 99))),
                }
            )

        top_datasource = [
            {
                "datasource_id": datasource_id,
                "datasource_name": datasource_name_map.get(datasource_id),
                "count": count,
            }
            for datasource_id, count in datasource_counter.most_common(top_n)
        ]

        return {
            "success": True,
            "scope": normalized_scope,
            "overview": {
                "total": len(records),
                "window_hours": round((window_end - window_start).total_seconds() / 3600, 2),
                "unique_datasource": len(datasource_counter),
                "active": status_counter.get("active", 0),
                "acknowledged": status_counter.get("acknowledged", 0),
                "resolved": status_counter.get("resolved", 0),
            },
            "by_severity": _counter_to_list(severity_counter),
            "by_status": _counter_to_list(status_counter),
            "by_alert_type": _counter_to_list(alert_type_counter),
            "by_event_category": _counter_to_list(event_category_counter),
            "by_fault_domain": _counter_to_list(fault_domain_counter),
            "trend": trend,
            "top_datasource": top_datasource,
            "top_metrics": _counter_to_list(metric_counter, top_n=top_n),
            "top_titles": _counter_to_list(title_counter, top_n=top_n),
            "filters": {
                "datasource_ids": datasource_id_list,
                "status": status,
                "severity": severity,
                "scope": normalized_scope,
            },
            "time_range": {
                "start_time": window_start.isoformat(),
                "end_time": window_end.isoformat(),
                "bucket": bucket_label,
            },
        }

    query = select(AlertMessage, AlertEvent.event_category, AlertEvent.fault_domain).join(
        AlertEvent,
        AlertMessage.event_id == AlertEvent.id,
        isouter=True,
    )
    if datasource_id_list:
        query = query.where(AlertMessage.datasource_id.in_(datasource_id_list))
    query = query.where(
        AlertMessage.created_at >= window_start,
        AlertMessage.created_at <= window_end,
    )
    if status and status != "all":
        query = query.where(AlertMessage.status == status)
    if severity:
        query = query.where(AlertMessage.severity == severity)

    result = await db.execute(query)
    rows = result.all()

    severity_counter = Counter()
    status_counter = Counter()
    alert_type_counter = Counter()
    event_category_counter = Counter()
    fault_domain_counter = Counter()
    datasource_counter = Counter()
    metric_counter = Counter()
    title_counter = Counter()
    bucket_map: dict[datetime, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "by_severity": Counter(),
            "by_status": Counter(),
        }
    )

    for alert, event_category, fault_domain in rows:
        severity_counter[alert.severity] += 1
        status_counter[alert.status] += 1
        alert_type_counter[alert.alert_type or "unknown"] += 1
        event_category_counter[event_category or "unknown"] += 1
        fault_domain_counter[fault_domain or "unknown"] += 1
        datasource_counter[alert.datasource_id] += 1
        if alert.metric_name:
            metric_counter[alert.metric_name] += 1
        if alert.title:
            title_counter[alert.title] += 1

        bucket_start = _floor_datetime(alert.created_at, bucket_delta)
        bucket_map[bucket_start]["count"] += 1
        bucket_map[bucket_start]["by_severity"][alert.severity] += 1
        bucket_map[bucket_start]["by_status"][alert.status] += 1

    trend = []
    for bucket_start in sorted(bucket_map.keys()):
        data = bucket_map[bucket_start]
        trend.append(
            {
                "bucket_start": bucket_start.isoformat(),
                "bucket_end": (bucket_start + bucket_delta).isoformat(),
                "count": data["count"],
                "by_severity": dict(sorted(data["by_severity"].items(), key=lambda item: SEVERITY_ORDER.get(item[0], 99))),
                "by_status": dict(sorted(data["by_status"].items(), key=lambda item: STATUS_ORDER.get(item[0], 99))),
            }
        )

    top_datasource = [
        {
            "datasource_id": datasource_id,
            "datasource_name": datasource_name_map.get(datasource_id),
            "count": count,
        }
        for datasource_id, count in datasource_counter.most_common(top_n)
    ]

    return {
        "success": True,
        "scope": normalized_scope,
        "overview": {
            "total": len(rows),
            "window_hours": round((window_end - window_start).total_seconds() / 3600, 2),
            "unique_datasource": len(datasource_counter),
            "active": status_counter.get("active", 0),
            "acknowledged": status_counter.get("acknowledged", 0),
            "resolved": status_counter.get("resolved", 0),
        },
        "by_severity": _counter_to_list(severity_counter),
        "by_status": _counter_to_list(status_counter),
        "by_alert_type": _counter_to_list(alert_type_counter),
        "by_event_category": _counter_to_list(event_category_counter),
        "by_fault_domain": _counter_to_list(fault_domain_counter),
        "trend": trend,
        "top_datasource": top_datasource,
        "top_metrics": _counter_to_list(metric_counter, top_n=top_n),
        "top_titles": _counter_to_list(title_counter, top_n=top_n),
        "filters": {
            "datasource_ids": datasource_id_list,
            "status": status,
            "severity": severity,
            "scope": normalized_scope,
        },
        "time_range": {
            "start_time": window_start.isoformat(),
            "end_time": window_end.isoformat(),
            "bucket": bucket_label,
        },
    }
