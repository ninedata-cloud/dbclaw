import json
import logging
import os
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.integration_executor import IntegrationExecutor
from backend.utils.integration_templates import ALIYUN_RDS_TEMPLATE


class _FakeRequest:
    def __init__(self, request_type: str):
        self.request_type = request_type
        self.params = {}

    def set_DBInstanceId(self, value):
        self.params["DBInstanceId"] = value

    def set_Key(self, value):
        self.params["Key"] = value

    def set_StartTime(self, value):
        self.params["StartTime"] = value

    def set_EndTime(self, value):
        self.params["EndTime"] = value

    def set_PageSize(self, value):
        self.params["PageSize"] = value


def _install_fake_aliyun_modules(responses_by_instance: dict[str, dict], recorded_requests: list[dict]):
    class FakeAcsClient:
        def __init__(self, access_key_id, access_key_secret, region_id):
            self.access_key_id = access_key_id
            self.access_key_secret = access_key_secret
            self.region_id = region_id

        def do_action_with_exception(self, request):
            if request.request_type == "list_instances":
                recorded_requests.append({"request_type": request.request_type, **request.params})
                return json.dumps({"Items": {"DBInstance": [{"DBInstanceId": "rm-preflight"}]}})

            recorded_requests.append({"request_type": request.request_type, **request.params})
            instance_id = request.params["DBInstanceId"]
            response = responses_by_instance[instance_id]
            if request.request_type == "describe_attribute":
                return json.dumps(response["attribute"])
            return json.dumps(response["performance"])

    client_module = types.ModuleType("aliyunsdkcore.client")
    client_module.AcsClient = FakeAcsClient

    core_module = types.ModuleType("aliyunsdkcore")
    core_module.client = client_module

    perf_request_module = types.ModuleType("DescribeDBInstancePerformanceRequest")
    perf_request_module.DescribeDBInstancePerformanceRequest = lambda: _FakeRequest("describe_performance")

    attr_request_module = types.ModuleType("DescribeDBInstanceAttributeRequest")
    attr_request_module.DescribeDBInstanceAttributeRequest = lambda: _FakeRequest("describe_attribute")

    instances_request_module = types.ModuleType("DescribeDBInstancesRequest")
    instances_request_module.DescribeDBInstancesRequest = lambda: _FakeRequest("list_instances")

    v20140815_module = types.ModuleType("aliyunsdkrds.request.v20140815")
    v20140815_module.DescribeDBInstancePerformanceRequest = perf_request_module
    v20140815_module.DescribeDBInstanceAttributeRequest = attr_request_module
    v20140815_module.DescribeDBInstancesRequest = instances_request_module

    request_module = types.ModuleType("aliyunsdkrds.request")
    request_module.v20140815 = v20140815_module

    rds_module = types.ModuleType("aliyunsdkrds")
    rds_module.request = request_module

    return {
        "aliyunsdkcore": core_module,
        "aliyunsdkcore.client": client_module,
        "aliyunsdkrds": rds_module,
        "aliyunsdkrds.request": request_module,
        "aliyunsdkrds.request.v20140815": v20140815_module,
    }


def _build_perf_response(items: list[tuple[str, str, str]]):
    return {
        "PerformanceKeys": {
            "PerformanceKey": [
                {
                    "Key": key,
                    "Values": {
                        "PerformanceValue": [
                            {
                                "Date": timestamp,
                                "Value": value,
                            }
                        ]
                    },
                }
                for key, timestamp, value in items
            ]
        }
    }


def _build_attribute_response(storage_gb: float, disk_used_bytes: int):
    return {
        "Items": {
            "DBInstanceAttribute": [
                {
                    "DBInstanceStorage": str(storage_gb),
                    "DBInstanceDiskUsed": str(disk_used_bytes),
                }
            ]
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("db_type", "instance_id", "response", "attribute_response", "expected_metrics", "expected_key_parts", "unexpected_key_parts"),
    [
        (
            "mysql",
            "rm-mysql-001",
            _build_perf_response(
                [
                    ("MySQL_MemCpuUsage", "2026-04-06T10:00:00Z", "61.5&74.2"),
                    ("MySQL_DetailedSpaceUsage", "2026-04-06T10:00:00Z", "153600&102400&20480&1024&512"),
                    ("MySQL_IOPS", "2026-04-06T10:00:00Z", "123"),
                    ("MySQL_MBPS", "2026-04-06T10:00:00Z", "2048"),
                    ("MySQL_NetworkTraffic", "2026-04-06T10:00:00Z", "512&768"),
                    ("MySQL_QPSTPS", "2026-04-06T10:00:00Z", "100&8"),
                    ("MySQL_Sessions", "2026-04-06T10:00:00Z", "12&34"),
                ]
            ),
            _build_attribute_response(200, 150 * 1024 * 1024 * 1024),
            {
                "cpu_usage": 61.5,
                "memory_usage": 74.2,
                "disk_total": 204800.0,
                "disk_used": 153600.0,
                "iops": 123.0,
                "throughput": 2048.0,
                "network_in": 512.0,
                "network_out": 768.0,
                "connections_active": 12.0,
                "connections_total": 34.0,
                "qps": 100.0,
                "tps": 8.0,
                "disk_usage": 75.0,
            },
            ["MySQL_MemCpuUsage", "MySQL_MBPS", "MySQL_Sessions"],
            ["SQLServer_QPS", "PgSQL_Session"],
        ),
        (
            "postgresql",
            "rm-pg-001",
            _build_perf_response(
                [
                    ("CpuUsage", "2026-04-06T10:05:00Z", "48.5"),
                    ("MemoryUsage", "2026-04-06T10:05:00Z", "66.1"),
                    ("PgSQL_SpaceUsage", "2026-04-06T10:05:00Z", str(100 * 1024 * 1024)),
                    ("PgSQL_IOPS", "2026-04-06T10:05:00Z", "88"),
                    ("PgSQL_Session", "2026-04-06T10:05:00Z", "19"),
                ]
            ),
            _build_attribute_response(300, 120 * 1024 * 1024 * 1024),
            {
                "cpu_usage": 48.5,
                "memory_usage": 66.1,
                "disk_total": 307200.0,
                "disk_used": 122880.0,
                "iops": 88.0,
                "total_connections": 19.0,
                "connections_total": 19.0,
                "disk_usage": 40.0,
            },
            ["CpuUsage", "MemoryUsage", "PgSQL_Session"],
            ["MySQL_QPSTPS", "SQLServer_QPS"],
        ),
        (
            "sqlserver",
            "rm-sqlserver-001",
            _build_perf_response(
                [
                    ("SQLServer_InstanceCPUUsage", "2026-04-06T10:10:00Z", "72.3"),
                    ("SQLServer_InstanceMemUsage", "2026-04-06T10:10:00Z", "81.4"),
                    ("SQLServer_InstanceDiskUsage", "2026-04-06T10:10:00Z", "63.2"),
                    ("SQLServer_DetailedSpaceUsage", "2026-04-06T10:10:00Z", "40960&30720&8192&1024&1024"),
                    ("SQLServer_IOPS", "2026-04-06T10:10:00Z", "100&40&60"),
                    ("SQLServer_NetworkTraffic", "2026-04-06T10:10:00Z", "200&150"),
                    ("SQLServer_QPS", "2026-04-06T10:10:00Z", "900"),
                    ("SQLServer_Transactions", "2026-04-06T10:10:00Z", "45&12"),
                    ("SQLServer_Sessions", "2026-04-06T10:10:00Z", "2&5&3&7&11&13"),
                    ("SQLServer_BufferHit", "2026-04-06T10:10:00Z", "99.5"),
                ]
            ),
            _build_attribute_response(80, int(50.56 * 1024 * 1024 * 1024)),
            {
                "cpu_usage": 72.3,
                "memory_usage": 81.4,
                "disk_usage": 63.2,
                "disk_total": 81920.0,
                "disk_used": 51773.44,
                "iops": 100.0,
                "disk_reads_per_sec": 40.0,
                "disk_writes_per_sec": 60.0,
                "network_out": 200.0,
                "network_in": 150.0,
                "qps": 900.0,
                "tps": 45.0,
                "active_transactions": 5.0,
                "active_connections": 7.0,
                "total_connections": 13.0,
                "cache_hit_rate": 99.5,
                "buffer_pool_hit_rate": 99.5,
            },
            ["SQLServer_InstanceCPUUsage", "SQLServer_Transactions", "SQLServer_Sessions"],
            ["MySQL_MemCpuUsage", "PgSQL_Session"],
        ),
    ],
)
async def test_aliyun_rds_template_supports_multiple_engines(
    db_type,
    instance_id,
    response,
    attribute_response,
    expected_metrics,
    expected_key_parts,
    unexpected_key_parts,
):
    recorded_requests = []
    fake_modules = _install_fake_aliyun_modules(
        {
            instance_id: {
                "performance": response,
                "attribute": attribute_response,
            }
        },
        recorded_requests,
    )
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))

    datasources = [
        {
            "id": 1,
            "name": f"test-{db_type}",
            "db_type": db_type,
            "external_instance_id": instance_id,
        }
    ]

    params = {
        "region_id": "cn-hangzhou",
        "access_key_id": "ak-test",
        "access_key_secret": "sk-test",
    }

    with patch.dict("sys.modules", fake_modules):
        metrics = await executor.execute_metric_collection(ALIYUN_RDS_TEMPLATE["code"], params, datasources)

    metrics_by_name = {item["metric_name"]: item for item in metrics}

    for metric_name, expected_value in expected_metrics.items():
        assert metric_name in metrics_by_name
        assert metrics_by_name[metric_name]["metric_value"] == expected_value

    assert metrics_by_name["cpu_usage"]["timestamp"].startswith("2026-04-06T10:")

    perf_requests = [item for item in recorded_requests if item["request_type"] == "describe_performance"]
    assert len(perf_requests) == 1
    attr_requests = [item for item in recorded_requests if item["request_type"] == "describe_attribute"]
    assert len(attr_requests) == 1
    requested_keys = perf_requests[0]["Key"]
    assert perf_requests[0]["StartTime"].endswith("Z")
    assert perf_requests[0]["EndTime"].endswith("Z")
    assert len(perf_requests[0]["StartTime"]) == 17
    assert len(perf_requests[0]["EndTime"]) == 17
    assert perf_requests[0]["StartTime"].count(":") == 1
    assert perf_requests[0]["EndTime"].count(":") == 1
    for key_part in expected_key_parts:
        assert key_part in requested_keys
    for key_part in unexpected_key_parts:
        assert key_part not in requested_keys
    assert attr_requests[0]["DBInstanceId"] == instance_id


@pytest.mark.asyncio
async def test_aliyun_rds_template_rejects_unsupported_db_type():
    recorded_requests = []
    fake_modules = _install_fake_aliyun_modules({}, recorded_requests)
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))

    datasources = [
        {
            "id": 1,
            "name": "test-oracle",
            "db_type": "oracle",
            "external_instance_id": "rm-oracle-001",
        }
    ]

    params = {
        "region_id": "cn-hangzhou",
        "access_key_id": "ak-test",
        "access_key_secret": "sk-test",
    }

    with patch.dict("sys.modules", fake_modules):
        with pytest.raises(ValueError, match="暂不支持阿里云 RDS 外部采集"):
            await executor.execute_metric_collection(ALIYUN_RDS_TEMPLATE["code"], params, datasources)


@pytest.mark.asyncio
async def test_aliyun_mysql_prefers_mysql_mem_cpu_usage_over_rcu_variant():
    recorded_requests = []
    instance_id = "rm-mysql-priority"
    response = _build_perf_response(
        [
            ("MySQL_MemCpuUsage", "2026-04-06T10:00:00Z", "0.83&16.38"),
            ("MySQL_RCU_MemCpuUsage", "2026-04-06T10:00:00Z", "16.38&0.83"),
        ]
    )
    fake_modules = _install_fake_aliyun_modules(
        {
            instance_id: {
                "performance": response,
                "attribute": _build_attribute_response(100, 16 * 1024 * 1024 * 1024),
            }
        },
        recorded_requests,
    )
    executor = IntegrationExecutor(AsyncMock(), logging.getLogger(__name__))

    datasources = [
        {
            "id": 1,
            "name": "test-mysql-priority",
            "db_type": "mysql",
            "external_instance_id": instance_id,
        }
    ]

    params = {
        "region_id": "cn-hangzhou",
        "access_key_id": "ak-test",
        "access_key_secret": "sk-test",
    }

    with patch.dict("sys.modules", fake_modules):
        metrics = await executor.execute_metric_collection(ALIYUN_RDS_TEMPLATE["code"], params, datasources)

    metrics_by_name = {item["metric_name"]: item for item in metrics}

    assert metrics_by_name["cpu_usage"]["metric_value"] == 0.83
    assert metrics_by_name["memory_usage"]["metric_value"] == 16.38
