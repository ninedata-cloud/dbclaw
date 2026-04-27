from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MAX_VISUALIZED_METRICS_PER_PANEL = 6


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_summary(summary: Any) -> dict[str, float]:
    if not isinstance(summary, Mapping):
        return {}

    normalized: dict[str, float] = {}
    for key in ("avg", "min", "max", "last"):
        value = summary.get(key)
        if _is_number(value):
            normalized[key] = round(float(value), 4)
    return normalized


def _build_metric_label(metric_name: str) -> str:
    return str(metric_name or "").strip().replace("_", " ")


def _build_metric_visualization(metric_name: str, points: Sequence[Any], summary_map: Mapping[str, Any]) -> dict[str, Any] | None:
    series_points: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, Mapping):
            continue
        bucket_start = point.get("bucket_start")
        if not bucket_start:
            continue
        avg_value = point.get("avg")
        min_value = point.get("min")
        max_value = point.get("max")
        last_value = point.get("last")
        if not any(_is_number(candidate) for candidate in (avg_value, min_value, max_value, last_value)):
            continue

        series_points.append(
            {
                "time": str(bucket_start),
                "bucket_end": str(point.get("bucket_end") or ""),
                "avg": round(float(avg_value), 4) if _is_number(avg_value) else None,
                "min": round(float(min_value), 4) if _is_number(min_value) else None,
                "max": round(float(max_value), 4) if _is_number(max_value) else None,
                "last": round(float(last_value), 4) if _is_number(last_value) else None,
                "count": int(point.get("count") or 0),
            }
        )

    if not series_points:
        return None

    return {
        "name": metric_name,
        "label": _build_metric_label(metric_name),
        "point_count": len(series_points),
        "summary": _normalize_summary(summary_map.get(metric_name)),
        "points": series_points,
    }


def _build_panel(
    panel_key: str,
    title: str,
    payload: Mapping[str, Any],
    *,
    target_name: str | None = None,
) -> dict[str, Any] | None:
    if panel_key == "host" and payload.get("available") is False:
        return None

    series_map = payload.get("series")
    if not isinstance(series_map, Mapping) or not series_map:
        return None

    selected_metric_names = payload.get("selected_metric_names")
    if not isinstance(selected_metric_names, Sequence) or isinstance(selected_metric_names, (str, bytes)):
        selected_metric_names = list(series_map.keys())

    filtered_metric_names = [
        str(metric_name).strip()
        for metric_name in selected_metric_names
        if str(metric_name).strip() and isinstance(series_map.get(str(metric_name).strip()), Sequence)
    ]
    if not filtered_metric_names:
        return None

    summary_map = payload.get("summary")
    if not isinstance(summary_map, Mapping):
        summary_map = {}

    metrics: list[dict[str, Any]] = []
    for metric_name in filtered_metric_names[:MAX_VISUALIZED_METRICS_PER_PANEL]:
        metric_visualization = _build_metric_visualization(metric_name, series_map.get(metric_name) or [], summary_map)
        if metric_visualization:
            metrics.append(metric_visualization)

    if not metrics:
        return None

    return {
        "panel_key": panel_key,
        "title": title,
        "target_name": target_name,
        "hidden_metric_count": max(0, len(filtered_metric_names) - len(metrics)),
        "metrics": metrics,
    }


def build_tool_result_visualization(tool_name: str, result: Any) -> dict[str, Any] | None:
    if tool_name != "query_monitoring_history":
        return None
    if not isinstance(result, Mapping):
        return None
    if result.get("success") is False:
        return None

    aggregation = result.get("aggregation")
    if not isinstance(aggregation, Mapping):
        aggregation = {}

    datasource_meta = result.get("datasource")
    if not isinstance(datasource_meta, Mapping):
        datasource_meta = {}

    host_meta = result.get("host")
    if not isinstance(host_meta, Mapping):
        host_meta = {}

    panels: list[dict[str, Any]] = []

    datasource_panel = _build_panel(
        "datasource",
        "数据源监控趋势",
        result.get("datasource_metric") if isinstance(result.get("datasource_metric"), Mapping) else {},
        target_name=str(datasource_meta.get("name") or "").strip() or None,
    )
    if datasource_panel:
        panels.append(datasource_panel)

    host_target_name = str(host_meta.get("name") or host_meta.get("host") or "").strip() or None
    host_panel = _build_panel(
        "host",
        "主机监控趋势",
        result.get("host_metric") if isinstance(result.get("host_metric"), Mapping) else {},
        target_name=host_target_name,
    )
    if host_panel:
        panels.append(host_panel)

    if not panels:
        return None

    time_range = result.get("time_range")
    if not isinstance(time_range, Mapping):
        time_range = {}

    return {
        "type": "monitoring_history",
        "title": "监控历史曲线",
        "datasource_id": datasource_meta.get("id"),
        "datasource_name": datasource_meta.get("name"),
        "time_range": {
            "start_time": time_range.get("start_time"),
            "end_time": time_range.get("end_time"),
        },
        "aggregation": {
            "bucket_seconds": aggregation.get("bucket_seconds"),
            "bucket_label": aggregation.get("bucket_label"),
            "max_points": aggregation.get("max_points"),
        },
        "panels": panels,
    }
