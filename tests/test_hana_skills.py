#!/usr/bin/env python3
"""
Test suite for SAP HANA diagnostic skills
"""
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.skills.loader import SkillLoader


class FakeHANAConnection:
    """Mock HANA connection for testing"""

    async def get_status(self):
        return {
            "connections_active": 10,
            "connections_total": 50,
            "connections_idle": 40,
            "transactions_active": 5,
            "lock_waiting": 2,
            "db_size_bytes": 1073741824,
            "used_memory_bytes": 536870912,
            "total_memory_bytes": 1073741824,
            "uptime": 86400,
        }

    async def get_process_list(self):
        return [
            {
                "id": 123,
                "user": "SYSTEM",
                "host": "192.168.1.100",
                "db": "SYSTEMDB",
                "command": "RUNNING",
                "time": 10,
                "state": "EXECUTING",
                "info": None,
            }
        ]

    async def get_slow_queries(self):
        return [
            {
                "query": "SELECT * FROM LARGE_TABLE",
                "duration": 15.5,
                "start_time": "2026-04-19 10:00:00",
                "user": "APP_USER",
                "connection_id": 456,
            }
        ]

    async def get_variables(self):
        return {
            "max_connections": "500",
            "indexserver/sql/sql_executors": "4",
        }

    async def get_table_stats(self):
        return [
            {
                "schema": "MYSCHEMA",
                "table": "ORDERS",
                "rows": 1000000,
                "disk_size": 104857600,
                "memory_size": 52428800,
            }
        ]

    async def get_replication_status(self):
        return {
            "enabled": True,
            "mode": "SYNC",
            "status": "ACTIVE",
            "secondary_host": "hana-secondary",
            "secondary_port": 30013,
        }

    async def explain_query(self, sql):
        return {
            "plan": [
                {"line": "TABLE SCAN on ORDERS"},
                {"line": "FILTER: ORDER_DATE > '2026-01-01'"},
            ]
        }

    async def get_db_size(self):
        return {
            "database": "SYSTEMDB",
            "total_size_bytes": 2147483648,
            "data_size_bytes": 1610612736,
            "log_size_bytes": 536870912,
        }

    async def get_index_stats(self):
        return [
            {
                "schema": "MYSCHEMA",
                "table": "ORDERS",
                "index": "IDX_ORDER_DATE",
                "type": "BTREE",
                "size_bytes": 10485760,
            }
        ]

    async def get_table_fragmentation(self):
        return [
            {
                "schema": "MYSCHEMA",
                "table": "ORDERS",
                "rows": 1000000,
                "disk_size": 104857600,
                "memory_size": 52428800,
                "fragmentation_pct": 50.0,
            }
        ]

    async def get_lock_waits(self):
        return [
            {
                "waiting_connection": 789,
                "waiting_statement": 101,
                "blocking_connection": 456,
                "blocking_statement": 99,
                "lock_type": "RECORD",
                "lock_mode": "EXCLUSIVE",
            }
        ]

    async def terminate_session(self, session_id):
        return {"success": True, "message": f"Session {session_id} terminated"}


class FakeContext:
    """Mock skill execution context"""

    async def execute_query(self, sql, datasource_id):
        """Return mock data based on SQL query"""
        sql_upper = sql.upper()

        # Process list (must check before connection statistics)
        if "M_CONNECTIONS" in sql_upper and "IDLE_TIME" in sql_upper:
            return {
                "success": True,
                "data": [[123, "SYSTEM", "192.168.1.100", "RUNNING", 1, "EXECUTING", "SYSTEMDB", 10000]],
                "columns": ["CONNECTION_ID", "USER_NAME", "CLIENT_IP", "CONNECTION_STATUS", "CURRENT_STATEMENT_ID", "LAST_ACTION", "CURRENT_SCHEMA_NAME", "IDLE_TIME"]
            }

        # Connection statistics
        if "M_CONNECTIONS" in sql_upper and "CONNECTION_STATUS" in sql_upper:
            return {"success": True, "data": [[50, 10, 40]], "columns": ["total", "active", "idle"]}

        # Transaction count
        if "M_TRANSACTIONS" in sql_upper:
            return {"success": True, "data": [[5]], "columns": ["tx_count"]}

        # Memory usage
        if "M_SERVICE_MEMORY" in sql_upper:
            return {"success": True, "data": [[536870912, 1073741824]], "columns": ["used_memory", "total_memory"]}

        # DB size detail (must check before database size)
        if "M_TABLE_PERSISTENCE_STATISTICS" in sql_upper and "SUM(MEMORY_SIZE_IN_TOTAL)" in sql_upper:
            return {
                "success": True,
                "data": [[2147483648, 1610612736]],
                "columns": ["total_size", "memory_size"]
            }

        # Database size
        if "M_TABLE_PERSISTENCE_STATISTICS" in sql_upper and "SUM(DISK_SIZE)" in sql_upper:
            return {"success": True, "data": [[1073741824]], "columns": ["db_size"]}

        # Uptime
        if "M_DATABASE" in sql_upper and "SECONDS_BETWEEN" in sql_upper:
            return {"success": True, "data": [[86400]], "columns": ["uptime"]}

        # Lock waits detail (must check before lock waits count)
        if "M_BLOCKED_TRANSACTIONS" in sql_upper and "WAITING_CONNECTION_ID" in sql_upper:
            return {
                "success": True,
                "data": [[789, 101, 456, 99, "RECORD", "EXCLUSIVE", 5000]],
                "columns": ["WAITING_CONNECTION_ID", "WAITING_STATEMENT_ID", "BLOCKING_CONNECTION_ID", "BLOCKING_STATEMENT_ID", "LOCK_TYPE", "LOCK_MODE", "LOCK_WAIT_TIME"]
            }

        # Lock waits count
        if "M_BLOCKED_TRANSACTIONS" in sql_upper and "COUNT(*)" in sql_upper:
            return {"success": True, "data": [[2]], "columns": ["cnt"]}

        # Slow queries
        if "M_EXPENSIVE_STATEMENTS" in sql_upper:
            return {
                "success": True,
                "data": [["SELECT * FROM LARGE_TABLE", 15.5, "2026-04-19 10:00:00", "APP_USER", 456]],
                "columns": ["STATEMENT_STRING", "duration_sec", "START_TIME", "USER_NAME", "CONNECTION_ID"]
            }

        # Variables
        if "M_INIFILE_CONTENTS" in sql_upper:
            return {
                "success": True,
                "data": [["max_connections", "500"], ["indexserver/sql/sql_executors", "4"]],
                "columns": ["KEY", "VALUE"]
            }

        # Table fragmentation (must check before table stats)
        if "M_TABLES" in sql_upper and "NULLIF(DISK_SIZE, 0)" in sql_upper:
            return {
                "success": True,
                "data": [["MYSCHEMA", "ORDERS", 1000000, 104857600, 52428800, 50.0]],
                "columns": ["SCHEMA_NAME", "TABLE_NAME", "RECORD_COUNT", "DISK_SIZE", "MEMORY_SIZE_IN_TOTAL", "fragmentation_pct"]
            }

        # Table stats
        if "M_TABLES" in sql_upper and "RECORD_COUNT" in sql_upper:
            return {
                "success": True,
                "data": [["MYSCHEMA", "ORDERS", 1000000, 104857600, 52428800]],
                "columns": ["SCHEMA_NAME", "TABLE_NAME", "RECORD_COUNT", "DISK_SIZE", "MEMORY_SIZE_IN_TOTAL"]
            }

        # Replication status
        if "M_SERVICE_REPLICATION" in sql_upper:
            return {
                "success": True,
                "data": [["PRIMARY", "hana-primary", 30013, "SYNC", "ACTIVE", "YES", "2026-04-19 10:00:00", "2026-04-19 10:00:01"]],
                "columns": ["SITE_NAME", "HOST", "PORT", "REPLICATION_MODE", "REPLICATION_STATUS", "SECONDARY_ACTIVE_STATUS", "SHIPPED_LOG_POSITION_TIME", "LAST_LOG_POSITION_TIME"]
            }

        # Explain query
        if "EXPLAIN PLAN FOR" in sql_upper:
            return {
                "success": True,
                "data": [["TABLE SCAN on ORDERS"], ["FILTER: ORDER_DATE > '2026-01-01'"]],
                "columns": ["OPERATOR_NAME"]
            }

        # Index stats
        if "M_INDEXES" in sql_upper:
            return {
                "success": True,
                "data": [["MYSCHEMA", "ORDERS", "IDX_ORDER_DATE", "BTREE", 10485760, 5242880]],
                "columns": ["SCHEMA_NAME", "TABLE_NAME", "INDEX_NAME", "INDEX_TYPE", "MEMORY_SIZE", "DISK_SIZE"]
            }

        # Terminate session
        if "ALTER SYSTEM DISCONNECT SESSION" in sql_upper:
            return {"success": True, "data": [], "columns": []}

        return {"success": True, "data": [], "columns": []}


def _load_skill_executor(skill_name: str):
    """Load skill executor function from YAML file"""
    yaml_path = Path("backend/skills/builtin") / skill_name
    skill_def = SkillLoader.load_from_yaml(yaml_path.read_text())
    namespace = {}
    exec(skill_def.code, namespace)
    return namespace["execute"]


def test_all_hana_builtin_skills_exist():
    """Verify all expected HANA skills are present"""
    expected_skills = [
        "hana_get_db_status.yaml",
        "hana_get_process_list.yaml",
        "hana_get_slow_queries.yaml",
        "hana_get_variables.yaml",
        "hana_get_table_stats.yaml",
        "hana_get_replication_status.yaml",
        "hana_explain_query.yaml",
        "hana_get_db_size.yaml",
        "hana_get_index_stats.yaml",
        "hana_get_table_fragmentation.yaml",
        "hana_get_lock_waits.yaml",
        "hana_terminate_session.yaml",
    ]

    builtin_dir = Path("backend/skills/builtin")
    for skill_file in expected_skills:
        assert (builtin_dir / skill_file).exists(), f"Missing skill: {skill_file}"


@pytest.mark.asyncio
async def test_hana_get_db_status():
    """Test HANA database status skill"""
    execute = _load_skill_executor("hana_get_db_status.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "metrics" in result
    metrics = result["metrics"]
    assert metrics["connections_active"] == 10
    assert metrics["connections_total"] == 50
    assert metrics["transactions_active"] == 5
    assert metrics["lock_waiting"] == 2


@pytest.mark.asyncio
async def test_hana_get_process_list():
    """Test HANA process list skill"""
    execute = _load_skill_executor("hana_get_process_list.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "processes" in result
    assert result["count"] == 1
    assert result["processes"][0]["user"] == "SYSTEM"


@pytest.mark.asyncio
async def test_hana_get_slow_queries():
    """Test HANA slow queries skill"""
    execute = _load_skill_executor("hana_get_slow_queries.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "slow_queries" in result
    assert result["count"] == 1
    assert result["slow_queries"][0]["duration"] == 15.5


@pytest.mark.asyncio
async def test_hana_get_variables():
    """Test HANA configuration variables skill"""
    execute = _load_skill_executor("hana_get_variables.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "variables" in result
    assert result["count"] == 2
    assert "max_connections" in result["variables"]


@pytest.mark.asyncio
async def test_hana_get_table_stats():
    """Test HANA table statistics skill"""
    execute = _load_skill_executor("hana_get_table_stats.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "tables" in result
    assert result["count"] == 1
    assert result["tables"][0]["schema"] == "MYSCHEMA"
    assert result["tables"][0]["rows"] == 1000000


@pytest.mark.asyncio
async def test_hana_get_replication_status():
    """Test HANA replication status skill"""
    execute = _load_skill_executor("hana_get_replication_status.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "replication_status" in result
    assert len(result["replication_status"]) > 0
    assert result["replication_status"][0]["mode"] == "SYNC"


@pytest.mark.asyncio
async def test_hana_explain_query():
    """Test HANA explain query skill"""
    execute = _load_skill_executor("hana_explain_query.yaml")
    context = FakeContext()

    result = await execute(context, {
        "datasource_id": 1,
        "sql": "SELECT * FROM ORDERS WHERE ORDER_DATE > '2026-01-01'"
    })

    assert result["success"] is True
    assert "plan" in result
    assert len(result["plan"]) == 2


@pytest.mark.asyncio
async def test_hana_get_db_size():
    """Test HANA database size skill"""
    execute = _load_skill_executor("hana_get_db_size.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "size_info" in result
    assert result["size_info"]["total_size_bytes"] == 2147483648
    assert result["size_info"]["memory_size_bytes"] == 1610612736


@pytest.mark.asyncio
async def test_hana_get_index_stats():
    """Test HANA index statistics skill"""
    execute = _load_skill_executor("hana_get_index_stats.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "indexes" in result
    assert result["count"] == 1
    assert result["indexes"][0]["index"] == "IDX_ORDER_DATE"


@pytest.mark.asyncio
async def test_hana_get_table_fragmentation():
    """Test HANA table fragmentation skill"""
    execute = _load_skill_executor("hana_get_table_fragmentation.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "tables" in result
    assert result["count"] == 1
    assert result["tables"][0]["fragmentation_pct"] == 50.0


@pytest.mark.asyncio
async def test_hana_get_lock_waits():
    """Test HANA lock waits skill"""
    execute = _load_skill_executor("hana_get_lock_waits.yaml")
    context = FakeContext()

    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is True
    assert "lock_waits" in result
    assert result["count"] == 1
    assert result["lock_waits"][0]["lock_type"] == "RECORD"


@pytest.mark.asyncio
async def test_hana_terminate_session():
    """Test HANA terminate session skill"""
    execute = _load_skill_executor("hana_terminate_session.yaml")
    context = FakeContext()

    result = await execute(context, {
        "datasource_id": 1,
        "session_id": 123
    })

    assert result["success"] is True
    assert "Session 123 terminated" in result["message"]


@pytest.mark.asyncio
async def test_hana_skills_handle_errors():
    """Test that HANA skills properly handle errors"""
    execute = _load_skill_executor("hana_get_process_list.yaml")

    class ErrorContext:
        async def execute_query(self, query, datasource_id):
            return {"success": False, "error": "Connection failed"}

    context = ErrorContext()
    result = await execute(context, {"datasource_id": 1})

    assert result["success"] is False
    assert "error" in result
    assert "Connection failed" in result["error"]
    assert "Connection failed" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
