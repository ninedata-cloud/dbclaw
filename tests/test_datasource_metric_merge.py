import pytest

from backend.services.datasource_metric_merge import (
    cleanup_obsolete_integration_keys,
    merge_integration_metric_data,
    merge_system_metric_data_for_integration,
)


@pytest.mark.unit
def test_merge_integration_metric_data_prefers_integration_keys():
    existing = {"cpu_usage": 10.0, "uptime": 3600, "qps": 1.0}
    incoming = {"cpu_usage": 88.0, "memory_usage": 72.0}
    merged = merge_integration_metric_data(existing, incoming)
    assert merged["cpu_usage"] == 88.0
    assert merged["memory_usage"] == 72.0
    assert merged["uptime"] == 3600
    assert merged["qps"] == 1.0


@pytest.mark.unit
def test_merge_integration_metric_data_setdefault_for_non_preferred():
    existing = {"foo": 1}
    incoming = {"foo": 2, "bar": 3}
    merged = merge_integration_metric_data(existing, incoming)
    assert merged["foo"] == 1
    assert merged["bar"] == 3


@pytest.mark.unit
def test_merge_system_metric_data_for_integration_keeps_preferred_when_present():
    existing = {"cpu_usage": 50.0, "uptime": 100}
    incoming = {"cpu_usage": 99.0, "uptime": 200}
    merged = merge_system_metric_data_for_integration(existing, incoming)
    assert merged["cpu_usage"] == 50.0
    assert merged["uptime"] == 200


@pytest.mark.unit
def test_merge_system_metric_data_handles_none_inputs():
    assert merge_integration_metric_data(None, None) == {}
    assert merge_system_metric_data_for_integration(None, {"a": 1}) == {"a": 1}


@pytest.mark.unit
def test_cleanup_obsolete_integration_keys_mysql_removes_aliases_when_canonical_present():
    data = {
        "connections_active": 1,
        "active_connections": 2,
        "total_connections": 3,
    }
    cleaned = cleanup_obsolete_integration_keys("mysql", data)
    assert "active_connections" not in cleaned
    assert "total_connections" not in cleaned
    assert cleaned["connections_active"] == 1


@pytest.mark.unit
def test_cleanup_obsolete_integration_keys_mysql_keeps_obsolete_without_canonical():
    data = {"active_connections": 2, "total_connections": 3}
    cleaned = cleanup_obsolete_integration_keys("mysql", data)
    assert cleaned == data


@pytest.mark.unit
def test_cleanup_obsolete_integration_keys_non_mysql_unchanged():
    data = {"active_connections": 1}
    assert cleanup_obsolete_integration_keys("postgresql", data) == data
