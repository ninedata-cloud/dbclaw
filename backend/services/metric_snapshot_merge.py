from typing import Any, Mapping


# 云监控更适合作为权威来源的性能指标。
# 对这些字段，外部集成值优先；直连采集只在字段缺失时补充。
INTEGRATION_PREFERRED_METRIC_KEYS = {
    "cpu_usage",
    "memory_usage",
    "disk_usage",
    "disk_total",
    "disk_data",
    "disk_log",
    "disk_temp",
    "disk_system",
    "iops",
    "throughput",
    "qps",
    "tps",
    "network_in",
    "network_out",
    "network_rx_bytes",
    "network_tx_bytes",
}

MYSQL_OBSOLETE_CONNECTION_KEYS = {
    "active_connections",
    "total_connections",
}


def merge_integration_metric_data(
    existing_data: Mapping[str, Any] | None,
    incoming_data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    合并外部集成指标。

    - 对云监控优先字段，使用 incoming 覆盖 existing
    - 对其他字段，仅在 existing 缺失时补充，避免覆盖直连采集更可信的值
    """
    merged = dict(existing_data or {})
    for key, value in (incoming_data or {}).items():
        if key in INTEGRATION_PREFERRED_METRIC_KEYS:
            merged[key] = value
            continue
        merged.setdefault(key, value)
    return merged


def merge_system_metric_data_for_integration(
    existing_data: Mapping[str, Any] | None,
    incoming_data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    对 metric_source=integration 的数据源合并直连采集结果。

    - 对云监控优先字段，保留已有外部集成值
    - 对其余字段，使用直连采集结果刷新
    """
    merged = dict(existing_data or {})
    for key, value in (incoming_data or {}).items():
        if key in INTEGRATION_PREFERRED_METRIC_KEYS and key in merged:
            continue
        merged[key] = value
    return merged


def cleanup_obsolete_integration_keys(
    db_type: str | None,
    data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    清理已废弃或易歧义的外部集成字段。
    """
    cleaned = dict(data or {})
    db_key = (db_type or "").strip().lower()

    if db_key == "mysql":
        has_canonical_connection_fields = any(
            key in cleaned
            for key in ("connections_active", "connections_total", "threads_running", "threads_connected")
        )
        if has_canonical_connection_fields:
            for key in MYSQL_OBSOLETE_CONNECTION_KEYS:
                cleaned.pop(key, None)

    return cleaned
