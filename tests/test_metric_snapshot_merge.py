from backend.services.metric_snapshot_merge import (
    INTEGRATION_PREFERRED_METRIC_KEYS,
    cleanup_obsolete_integration_keys,
    merge_integration_metric_data,
    merge_system_metric_data_for_integration,
)


def test_merge_integration_metric_data_prefers_cloud_performance_fields():
    existing = {
        "cpu_usage": 8.5,
        "memory_usage": 12.0,
        "qps": 1.2,
        "tps": 0.0,
        "connections_total": 8,
        "max_connections": 1120,
        "bytes_received": 1000,
    }
    incoming = {
        "cpu_usage": 16.4,
        "memory_usage": 0.82,
        "qps": 5.2,
        "tps": 0.33,
        "connections_total": 0.0,
        "network_in": 5.34,
    }

    merged = merge_integration_metric_data(existing, incoming)

    assert merged["cpu_usage"] == 16.4
    assert merged["memory_usage"] == 0.82
    assert merged["qps"] == 5.2
    assert merged["tps"] == 0.33
    assert merged["network_in"] == 5.34
    assert merged["connections_total"] == 8
    assert merged["max_connections"] == 1120
    assert merged["bytes_received"] == 1000


def test_merge_system_metric_data_for_integration_preserves_cloud_owned_fields():
    existing = {
        "cpu_usage": 16.4,
        "memory_usage": 0.82,
        "qps": 5.2,
        "tps": 0.33,
        "network_in": 5.34,
        "connections_total": 0.0,
        "max_connections": 1120,
    }
    incoming = {
        "cpu_usage": 7.8,
        "memory_usage": 15.0,
        "qps": 4.6,
        "tps": 0.0,
        "connections_total": 8,
        "max_connections": 2048,
        "bytes_received": 2048,
    }

    merged = merge_system_metric_data_for_integration(existing, incoming)

    assert merged["cpu_usage"] == 16.4
    assert merged["memory_usage"] == 0.82
    assert merged["qps"] == 5.2
    assert merged["tps"] == 0.33
    assert merged["network_in"] == 5.34
    assert merged["connections_total"] == 8
    assert merged["max_connections"] == 2048
    assert merged["bytes_received"] == 2048


def test_integration_preferred_metric_keys_excludes_connection_counters():
    assert "cpu_usage" in INTEGRATION_PREFERRED_METRIC_KEYS
    assert "memory_usage" in INTEGRATION_PREFERRED_METRIC_KEYS
    assert "qps" in INTEGRATION_PREFERRED_METRIC_KEYS
    assert "tps" in INTEGRATION_PREFERRED_METRIC_KEYS
    assert "connections_total" not in INTEGRATION_PREFERRED_METRIC_KEYS
    assert "connections_active" not in INTEGRATION_PREFERRED_METRIC_KEYS


def test_cleanup_obsolete_integration_keys_removes_mysql_ambiguous_aliases():
    data = {
        "connections_active": 0,
        "connections_total": 8,
        "threads_running": 1,
        "threads_connected": 8,
        "active_connections": 1,
        "total_connections": 0,
        "cpu_usage": 16.3,
    }

    cleaned = cleanup_obsolete_integration_keys("mysql", data)

    assert cleaned["connections_active"] == 0
    assert cleaned["connections_total"] == 8
    assert cleaned["threads_running"] == 1
    assert cleaned["threads_connected"] == 8
    assert "active_connections" not in cleaned
    assert "total_connections" not in cleaned
