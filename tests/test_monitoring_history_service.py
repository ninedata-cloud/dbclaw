from datetime import datetime, timedelta

from backend.services.monitoring_history_service import (
    aggregate_metric_records,
    resolve_bucket_seconds,
    select_metric_names,
)


def test_resolve_bucket_seconds_auto_scales_with_time_range():
    start = datetime(2026, 4, 8, 0, 0, 0)
    end = start + timedelta(hours=24)

    bucket_seconds = resolve_bucket_seconds(start, end, aggregate="auto", max_points=96)

    assert bucket_seconds >= 900
    assert bucket_seconds <= 3600


def test_select_metric_names_prefers_common_metrics():
    records = [
        (datetime(2026, 4, 8, 0, 0, 0), {"cpu_usage": 10, "qps": 100, "custom_metric": 1}),
        (datetime(2026, 4, 8, 0, 1, 0), {"cpu_usage": 12, "qps": 120}),
    ]

    selected, available = select_metric_names(
        records,
        preferred_metric_names=["cpu_usage", "memory_usage", "qps"],
        max_metrics=3,
    )

    assert available == ["cpu_usage", "custom_metric", "qps"]
    assert selected[:2] == ["cpu_usage", "qps"]


def test_aggregate_metric_records_groups_values_by_bucket():
    start = datetime(2026, 4, 8, 0, 0, 0)
    records = [
        (start, {"cpu_usage": 10, "qps": 100}),
        (start + timedelta(minutes=2), {"cpu_usage": 20, "qps": 120}),
        (start + timedelta(minutes=7), {"cpu_usage": 30, "qps": 140}),
    ]

    aggregated = aggregate_metric_records(
        records,
        metric_names=["cpu_usage", "qps"],
        bucket_seconds=300,
    )

    cpu_series = aggregated["series"]["cpu_usage"]
    qps_series = aggregated["series"]["qps"]

    assert aggregated["bucket_count"] == 2
    assert len(cpu_series) == 2
    assert cpu_series[0]["avg"] == 15.0
    assert cpu_series[0]["min"] == 10.0
    assert cpu_series[0]["max"] == 20.0
    assert cpu_series[0]["last"] == 20.0
    assert qps_series[1]["avg"] == 140.0
    assert aggregated["summary"]["cpu_usage"]["last"] == 30.0
