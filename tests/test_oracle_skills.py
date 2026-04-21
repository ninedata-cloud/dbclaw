#!/usr/bin/env python3
"""
Oracle builtin skill regression tests.
"""
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.database as database_module
import backend.services.oracle_service as oracle_service_module
from backend.skills.loader import SkillLoader


class SequentialQueryContext:
    """Return canned query results in call order and record issued SQL."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.queries = []

    async def execute_query(self, sql, datasource_id):
        self.queries.append((sql, datasource_id))
        if not self._responses:
            raise AssertionError(f"Unexpected query for datasource {datasource_id}: {sql}")
        return self._responses.pop(0)


def _load_skill_executor(skill_name: str):
    yaml_path = Path("backend/skills/builtin") / skill_name
    skill_def = SkillLoader.load_from_yaml(yaml_path.read_text())
    namespace = {}
    exec(skill_def.code, namespace)
    return namespace["execute"]


def test_all_oracle_builtin_skills_exist():
    expected_skills = [
        "oracle_explain_query.yaml",
        "oracle_get_db_status.yaml",
        "oracle_get_slow_queries.yaml",
        "oracle_get_table_stats.yaml",
        "oracle_get_tablespace_usage.yaml",
        "oracle_get_wait_events.yaml",
        "oracle_list_sessions.yaml",
    ]

    builtin_dir = Path("backend/skills/builtin")
    for skill_file in expected_skills:
        assert (builtin_dir / skill_file).exists(), f"Missing skill: {skill_file}"


@pytest.mark.asyncio
async def test_oracle_get_db_status_returns_metrics_and_sections():
    execute = _load_skill_executor("oracle_get_db_status.yaml")
    context = SequentialQueryContext(
        [
            {"success": True, "data": [[12, 3, 9]], "columns": ["total_sessions", "active_sessions", "inactive_sessions"]},
            {"success": True, "data": [["Buffer Cache", 512.0]], "columns": ["name", "size_mb"]},
            {"success": True, "data": [["ORCL", "READ WRITE", "ARCHIVELOG", "PRIMARY", "Linux"]], "columns": ["db_name", "open_mode", "log_mode", "database_role", "platform_name"]},
            {"success": True, "data": [["ORCL1", "db-host", "19c", "2026-04-01 08:00:00", "OPEN", 480.5]], "columns": ["instance_name", "host_name", "version", "startup_time", "status", "uptime_hours"]},
        ]
    )

    result = await execute(context, {"datasource_id": 11})

    assert result["success"] is True
    assert result["metrics"] == {
        "total_sessions": 12,
        "active_sessions": 3,
        "inactive_sessions": 9,
    }
    assert result["sga_info"] == [["Buffer Cache", 512.0]]
    assert result["database_info"] == [["ORCL", "READ WRITE", "ARCHIVELOG", "PRIMARY", "Linux"]]
    assert result["instance_info"] == [["ORCL1", "db-host", "19c", "2026-04-01 08:00:00", "OPEN", 480.5]]
    assert len(context.queries) == 4
    assert all(datasource_id == 11 for _, datasource_id in context.queries)
    assert "FROM V$SESSION" in context.queries[0][0].upper()
    assert "FROM V$SGA" in context.queries[1][0].upper()
    assert "FROM V$DATABASE" in context.queries[2][0].upper()
    assert "FROM V$INSTANCE" in context.queries[3][0].upper()


@pytest.mark.asyncio
async def test_oracle_get_db_status_returns_error_when_session_query_fails():
    execute = _load_skill_executor("oracle_get_db_status.yaml")
    context = SequentialQueryContext(
        [{"success": False, "error": "ORA-00942: table or view does not exist"}]
    )

    result = await execute(context, {"datasource_id": 12})

    assert result["success"] is False
    assert "ORA-00942" in result["error"]


@pytest.mark.asyncio
async def test_oracle_get_slow_queries_returns_rows_and_columns():
    execute = _load_skill_executor("oracle_get_slow_queries.yaml")
    context = SequentialQueryContext(
        [
            {
                "success": True,
                "data": [["8abc123", "SELECT * FROM ORDERS", 15, 30.2]],
                "columns": ["sql_id", "sql_text", "executions", "elapsed_seconds"],
            }
        ]
    )

    result = await execute(context, {"datasource_id": 13, "limit": 15})

    assert result["success"] is True
    assert result["queries"] == [["8abc123", "SELECT * FROM ORDERS", 15, 30.2]]
    assert result["columns"] == ["sql_id", "sql_text", "executions", "elapsed_seconds"]
    assert "FROM V$SQL" in context.queries[0][0].upper()
    assert "ROWNUM <= 15" in context.queries[0][0].upper()


@pytest.mark.asyncio
async def test_oracle_get_table_stats_returns_rows_and_columns():
    execute = _load_skill_executor("oracle_get_table_stats.yaml")
    context = SequentialQueryContext(
        [
            {
                "success": True,
                "data": [["APP", "ORDERS", 1000000, 2048, 0, 128, 16.0, "2026-04-20 09:00:00", "NO", "DISABLED", "1"]],
                "columns": ["owner", "table_name", "num_rows", "blocks", "empty_blocks", "avg_row_len", "size_mb", "last_analyzed", "partitioned", "compression", "parallel_degree"],
            }
        ]
    )

    result = await execute(context, {"datasource_id": 14})

    assert result["success"] is True
    assert result["tables"][0][1] == "ORDERS"
    assert result["columns"][0] == "owner"
    query = context.queries[0][0].upper()
    assert "FROM DBA_TABLES" in query
    assert "ROWNUM <= 100" in query


@pytest.mark.asyncio
async def test_oracle_get_tablespace_usage_returns_rows_and_columns():
    execute = _load_skill_executor("oracle_get_tablespace_usage.yaml")
    context = SequentialQueryContext(
        [
            {
                "success": True,
                "data": [["USERS", 1024.0, 768.0, 256.0, 75.0, 4, "YES"]],
                "columns": ["tablespace_name", "total_mb", "used_mb", "free_mb", "used_percent", "datafile_count", "autoextensible"],
            }
        ]
    )

    result = await execute(context, {"datasource_id": 15})

    assert result["success"] is True
    assert result["tablespaces"][0][0] == "USERS"
    assert result["columns"][4] == "used_percent"
    query = context.queries[0][0].upper()
    assert "FROM DBA_DATA_FILES" in query
    assert "FROM DBA_FREE_SPACE" in query


@pytest.mark.asyncio
async def test_oracle_get_wait_events_returns_rows_and_columns():
    execute = _load_skill_executor("oracle_get_wait_events.yaml")
    context = SequentialQueryContext(
        [
            {
                "success": True,
                "data": [["db file sequential read", "User I/O", 12345, 0, 22.3, 0.0018, 22.3]],
                "columns": ["event", "wait_class", "total_waits", "total_timeouts", "time_waited_seconds", "avg_wait_seconds", "time_waited_micro_seconds"],
            }
        ]
    )

    result = await execute(context, {"datasource_id": 16, "limit": 5})

    assert result["success"] is True
    assert result["wait_events"][0][0] == "db file sequential read"
    assert result["columns"][1] == "wait_class"
    query = context.queries[0][0].upper()
    assert "FROM V$SYSTEM_EVENT" in query
    assert "ROWNUM <= 5" in query


@pytest.mark.asyncio
async def test_oracle_list_sessions_returns_rows_and_columns():
    execute = _load_skill_executor("oracle_list_sessions.yaml")
    context = SequentialQueryContext(
        [
            {
                "success": True,
                "data": [[101, 202, "APP_USER", "ACTIVE", "oracle", "db-host", "sqlplus.exe", "JDBC Thin Client", "8abc123", "SELECT * FROM ORDERS", "2026-04-20 08:00:00", 30.5, None, "db file sequential read", "User I/O", 0.15]],
                "columns": ["sid", "serial#", "username", "status", "osuser", "machine", "program", "module", "sql_id", "sql_text", "logon_time", "session_duration_minutes", "blocking_session", "event", "wait_class", "wait_seconds"],
            }
        ]
    )

    result = await execute(context, {"datasource_id": 17})

    assert result["success"] is True
    assert result["sessions"][0][2] == "APP_USER"
    assert result["columns"][8] == "sql_id"
    query = context.queries[0][0].upper()
    assert "FROM V$SESSION S" in query
    assert "LEFT JOIN V$SQL" in query


@pytest.mark.asyncio
async def test_oracle_explain_query_uses_oracle_conn_mode_and_closes_connector(monkeypatch):
    execute = _load_skill_executor("oracle_explain_query.yaml")
    datasource = SimpleNamespace(
        id=21,
        db_type="oracle",
        host="127.0.0.1",
        port=1521,
        username="sys",
        password_encrypted=None,
        database="ORCL",
        extra_params={"oracle_conn_mode": "sysdba"},
    )

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = datasource
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=db_result)

    async def fake_get_db():
        yield fake_db

    captured = {}

    class FakeConnector:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def explain_sql(self, sql):
            captured["sql"] = sql
            return {
                "format": "tree",
                "plan": [{"operation": "TABLE ACCESS FULL", "object_name": "DUAL"}],
            }

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(database_module, "get_db", fake_get_db)
    monkeypatch.setattr(oracle_service_module, "OracleConnector", FakeConnector)

    result = await execute(object(), {"datasource_id": 21, "sql": "  SELECT * FROM dual  "})

    assert result == {
        "success": True,
        "format": "tree",
        "plan": [{"operation": "TABLE ACCESS FULL", "object_name": "DUAL"}],
    }
    assert captured["host"] == "127.0.0.1"
    assert captured["database"] == "ORCL"
    assert captured["oracle_conn_mode"] == "sysdba"
    assert captured["sql"] == "SELECT * FROM dual"
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_oracle_explain_query_rejects_non_oracle_datasource(monkeypatch):
    execute = _load_skill_executor("oracle_explain_query.yaml")
    datasource = SimpleNamespace(
        id=22,
        db_type="postgresql",
        host="127.0.0.1",
        port=5432,
        username="postgres",
        password_encrypted=None,
        database="dbclaw",
        extra_params=None,
    )

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = datasource
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=db_result)

    async def fake_get_db():
        yield fake_db

    monkeypatch.setattr(database_module, "get_db", fake_get_db)

    result = await execute(object(), {"datasource_id": 22, "sql": "SELECT 1"})

    assert result["success"] is False
    assert "only supports Oracle" in result["error"]
