import json
import logging
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.integration_executor import IntegrationExecutor
from backend.utils.integration_templates import HUAWEI_CLOUD_RDS_TEMPLATE


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.headers = headers or {}

    def json(self):
        return self._payload

    def header(self, name, default=None):
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return default


def _build_projects_response(project_id="project-test", project_name="cn-north-4"):
    payload = {"projects": [{"id": project_id, "name": project_name}]}
    return _FakeResponse(200, payload=payload)


def _build_metric_response(metric_values, timestamp_ms=1775469600000):
    metrics = []
    for metric_name, value in metric_values.items():
        metrics.append(
            {
                "namespace": "SYS.RDS",
                "metric_name": metric_name,
                "dimensions": [],
                "datapoints": [{"average": value, "timestamp": timestamp_ms}],
            }
        )
    return _FakeResponse(200, payload={"metrics": metrics})


async def _fake_get_system_config(self, key):
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("db_type", "instance_id", "remote_metric_values", "expected_metrics", "expected_remote_metrics", "unexpected_remote_metrics"),
    [
        (
            "mysql",
            "mysql-instance-001",
            {
                "rds001_cpu_util": 63.5,
                "rds002_mem_util": 74.2,
                "rds003_iops": 120.0,
                "rds004_bytes_in": 512.0,
                "rds005_bytes_out": 768.0,
                "rds006_conn_count": 40.0,
                "rds007_conn_active_count": 12.0,
                "rds008_qps": 320.0,
                "rds009_tps": 48.0,
                "rds039_disk_util": 55.1,
                "rds047_disk_total_size": 500.0,
                "rds048_disk_used_size": 275.0,
            },
            {
                "cpu_usage": 63.5,
                "memory_usage": 74.2,
                "iops": 120.0,
                "network_in": 512.0,
                "network_out": 768.0,
                "connections_total": 40.0,
                "total_connections": 40.0,
                "connections_active": 12.0,
                "active_connections": 12.0,
                "qps": 320.0,
                "tps": 48.0,
                "disk_usage": 55.1,
                "disk_total": 500.0,
                "disk_used": 275.0,
            },
            ["rds001_cpu_util", "rds008_qps", "rds047_disk_total_size"],
            ["rds082_tps", "rds054_db_connections_in_use"],
        ),
        (
            "postgresql",
            "postgres-instance-001",
            {
                "rds001_cpu_util": 49.3,
                "rds002_mem_util": 66.6,
                "rds003_iops": 88.0,
                "rds039_disk_util": 31.5,
                "rds042_database_connections": 28.0,
                "active_connections": 11.0,
                "read_count_per_second": 102.0,
                "write_count_per_second": 64.0,
                "rds082_tps": 23.0,
            },
            {
                "cpu_usage": 49.3,
                "memory_usage": 66.6,
                "iops": 88.0,
                "disk_usage": 31.5,
                "connections_total": 28.0,
                "total_connections": 28.0,
                "active_connections": 11.0,
                "connections_active": 11.0,
                "disk_reads_per_sec": 102.0,
                "disk_writes_per_sec": 64.0,
                "tps": 23.0,
            },
            ["rds042_database_connections", "active_connections", "rds082_tps"],
            ["rds056_batch_per_sec", "rds009_tps"],
        ),
        (
            "sqlserver",
            "sqlserver-instance-001",
            {
                "rds001_cpu_util": 70.0,
                "rds002_mem_util": 80.5,
                "rds003_iops": 150.0,
                "rds004_bytes_in": 640.0,
                "rds005_bytes_out": 320.0,
                "rds039_disk_util": 68.2,
                "rds054_db_connections_in_use": 15.0,
                "rds055_transactions_per_sec": 22.0,
                "rds056_batch_per_sec": 312.0,
                "rds059_cache_hit_ratio": 98.5,
            },
            {
                "cpu_usage": 70.0,
                "memory_usage": 80.5,
                "iops": 150.0,
                "network_in": 640.0,
                "network_out": 320.0,
                "disk_usage": 68.2,
                "active_connections": 15.0,
                "connections_active": 15.0,
                "tps": 22.0,
                "qps": 312.0,
                "batch_requests_per_sec": 312.0,
                "cache_hit_rate": 98.5,
                "buffer_pool_hit_rate": 98.5,
            },
            ["rds054_db_connections_in_use", "rds056_batch_per_sec", "rds059_cache_hit_ratio"],
            ["rds082_tps", "active_connections"],
        ),
    ],
)
async def test_huaweicloud_rds_template_supports_multiple_engines(
    db_type,
    instance_id,
    remote_metric_values,
    expected_metrics,
    expected_remote_metrics,
    unexpected_remote_metrics,
):
    recorded_requests = []
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))

    async def fake_http_request(self, method, url, **kwargs):
        recorded_requests.append(
            {
                "method": method,
                "url": url,
                "json": kwargs.get("json"),
                "data": kwargs.get("data"),
                "headers": kwargs.get("headers", {}),
            }
        )
        if url.endswith("/v3/projects"):
            return _build_projects_response()
        if url.endswith("/batch-query-metric-data"):
            return _build_metric_response(remote_metric_values)
        raise AssertionError(f"Unexpected request: {url}")

    datasource = [
        {
            "id": 1,
            "name": f"test-{db_type}",
            "db_type": db_type,
            "external_instance_id": instance_id,
        }
    ]
    params = {
        "region_id": "cn-north-4",
        "access_key_id": "test-ak",
        "access_key_secret": "test-sk",
    }

    with patch("backend.services.integration_executor.IntegrationContext.http_request", new=fake_http_request), patch(
        "backend.services.integration_executor.IntegrationContext.get_system_config",
        new=_fake_get_system_config,
    ):
        metrics = await executor.execute_metric_collection(HUAWEI_CLOUD_RDS_TEMPLATE["code"], params, datasource)

    metrics_by_name = {item["metric_name"]: item for item in metrics}
    for metric_name, expected_value in expected_metrics.items():
        assert metric_name in metrics_by_name
        assert metrics_by_name[metric_name]["metric_value"] == expected_value

    assert metrics_by_name["cpu_usage"]["labels"]["source"] == "huaweicloud_rds"
    assert metrics_by_name["cpu_usage"]["labels"]["instance_id"] == instance_id
    assert metrics_by_name["cpu_usage"]["timestamp"].endswith("Z")

    project_request = next(item for item in recorded_requests if item["url"].endswith("/v3/projects"))
    batch_request = next(item for item in recorded_requests if item["url"].endswith("/batch-query-metric-data"))
    batch_payload = json.loads(batch_request["data"])
    requested_remote_metrics = [metric["metric_name"] for metric in batch_payload["metrics"]]
    assert project_request["headers"]["Authorization"].startswith("SDK-HMAC-SHA256 Access=test-ak")
    assert batch_request["headers"]["Authorization"].startswith("SDK-HMAC-SHA256 Access=test-ak")
    assert "X-Auth-Token" not in batch_request["headers"]
    assert project_request["headers"]["X-Sdk-Date"]
    assert batch_payload["metrics"][0]["dimensions"][0]["value"] == instance_id
    for metric_name in expected_remote_metrics:
        assert metric_name in requested_remote_metrics
    for metric_name in unexpected_remote_metrics:
        assert metric_name not in requested_remote_metrics


@pytest.mark.asyncio
async def test_huaweicloud_rds_template_rejects_unsupported_db_type():
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))

    async def fake_http_request(self, method, url, **kwargs):
        if url.endswith("/v3/projects"):
            return _build_projects_response()
        raise AssertionError(f"Unexpected request: {url}")

    datasource = [
        {
            "id": 1,
            "name": "test-oracle",
            "db_type": "oracle",
            "external_instance_id": "oracle-instance-001",
        }
    ]
    params = {
        "region_id": "cn-north-4",
        "access_key_id": "test-ak",
        "access_key_secret": "test-sk",
    }

    with patch("backend.services.integration_executor.IntegrationContext.http_request", new=fake_http_request), patch(
        "backend.services.integration_executor.IntegrationContext.get_system_config",
        new=_fake_get_system_config,
    ):
        with pytest.raises(ValueError, match="暂不支持华为云 RDS 外部采集"):
            await executor.execute_metric_collection(HUAWEI_CLOUD_RDS_TEMPLATE["code"], params, datasource)


@pytest.mark.asyncio
async def test_huaweicloud_rds_template_validates_credentials_without_datasource():
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))
    recorded_urls = []

    async def fake_http_request(self, method, url, **kwargs):
        recorded_urls.append(url)
        if url.endswith("/v3/projects"):
            return _build_projects_response()
        raise AssertionError(f"Unexpected request: {url}")

    params = {
        "region_id": "cn-north-4",
        "access_key_id": "test-ak",
        "access_key_secret": "test-sk",
    }

    with patch("backend.services.integration_executor.IntegrationContext.http_request", new=fake_http_request), patch(
        "backend.services.integration_executor.IntegrationContext.get_system_config",
        new=_fake_get_system_config,
    ):
        metrics = await executor.execute_metric_collection(HUAWEI_CLOUD_RDS_TEMPLATE["code"], params, [])

    assert metrics == []
    assert recorded_urls == ["https://iam.cn-north-4.myhuaweicloud.com/v3/projects"]


@pytest.mark.asyncio
async def test_huaweicloud_postgresql_dimension_fallback_to_rds_cluster_id():
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))
    dimension_attempts = []

    async def fake_http_request(self, method, url, **kwargs):
        if url.endswith("/v3/projects"):
            return _build_projects_response()
        if url.endswith("/batch-query-metric-data"):
            dimension_name = json.loads(kwargs["data"])["metrics"][0]["dimensions"][0]["name"]
            dimension_attempts.append(dimension_name)
            if dimension_name == "postgresql_cluster_id":
                return _FakeResponse(400, payload={"error_msg": "invalid dimensions"}, text="invalid dimensions")
            return _build_metric_response(
                {
                    "rds001_cpu_util": 45.0,
                    "rds042_database_connections": 18.0,
                    "active_connections": 6.0,
                }
            )
        raise AssertionError(f"Unexpected request: {url}")

    datasource = [
        {
            "id": 9,
            "name": "test-postgresql-fallback",
            "db_type": "postgresql",
            "external_instance_id": "postgres-instance-fallback",
        }
    ]
    params = {
        "region_id": "cn-north-4",
        "access_key_id": "test-ak",
        "access_key_secret": "test-sk",
    }

    with patch("backend.services.integration_executor.IntegrationContext.http_request", new=fake_http_request), patch(
        "backend.services.integration_executor.IntegrationContext.get_system_config",
        new=_fake_get_system_config,
    ):
        metrics = await executor.execute_metric_collection(HUAWEI_CLOUD_RDS_TEMPLATE["code"], params, datasource)

    metrics_by_name = {item["metric_name"]: item for item in metrics}
    assert dimension_attempts == ["postgresql_cluster_id", "rds_cluster_id"]
    assert metrics_by_name["cpu_usage"]["metric_value"] == 45.0
    assert metrics_by_name["connections_total"]["metric_value"] == 18.0
    assert metrics_by_name["connections_active"]["metric_value"] == 6.0
