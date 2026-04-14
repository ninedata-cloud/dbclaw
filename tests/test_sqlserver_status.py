from unittest.mock import patch

import pytest

from backend.services.sqlserver_service import SQLServerConnector


class _FakeCursor:
    def __init__(self, fetchone_results, fetchall_results):
        self.fetchone_results = list(fetchone_results)
        self.fetchall_results = list(fetchall_results)
        self.executed_sql = []

    def execute(self, sql):
        self.executed_sql.append(sql)

    def fetchone(self):
        if not self.fetchone_results:
            return None
        return self.fetchone_results.pop(0)

    def fetchall(self):
        if not self.fetchall_results:
            return []
        return self.fetchall_results.pop(0)


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_sqlserver_status_uses_server_max_when_user_connections_is_zero():
    cursor = _FakeCursor(
        fetchone_results=[
            (20, 13, 1, 12, 0, None),
            (0,),
            (32767,),
            (1024,),
            (10, 20),
        ],
        fetchall_results=[[]],
    )
    conn = _FakeConnection(cursor)
    connector = SQLServerConnector(
        host="localhost",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    with patch.object(connector, "_connect", return_value=conn):
        result = await connector.get_status()

    assert result["connections_total"] == 13
    assert result["connections_active"] == 1
    assert result["max_connections"] == 32767
    assert any("@@MAX_CONNECTIONS" in sql for sql in cursor.executed_sql)
    assert conn.closed is True


@pytest.mark.asyncio
async def test_sqlserver_status_prefers_explicit_user_connections_limit():
    cursor = _FakeCursor(
        fetchone_results=[
            (20, 13, 1, 12, 0, None),
            (200,),
            (32767,),
            (1024,),
            (10, 20),
        ],
        fetchall_results=[[]],
    )
    conn = _FakeConnection(cursor)
    connector = SQLServerConnector(
        host="localhost",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    with patch.object(connector, "_connect", return_value=conn):
        result = await connector.get_status()

    assert result["max_connections"] == 200
    assert conn.closed is True


@pytest.mark.asyncio
async def test_sqlserver_variables_cast_sql_variant_values_to_text():
    cursor = _FakeCursor(
        fetchone_results=[],
        fetchall_results=[
            [
                ("affinity mask", "0"),
                ("max server memory (MB)", "2147483647"),
            ]
        ],
    )
    conn = _FakeConnection(cursor)
    connector = SQLServerConnector(
        host="localhost",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    with patch.object(connector, "_connect", return_value=conn):
        result = await connector.get_variables()

    executed_sql = cursor.executed_sql[0]
    assert "CONVERT(NVARCHAR(256), value_in_use)" in executed_sql
    assert "CONVERT(NVARCHAR(256), value)" in executed_sql
    assert result == {
        "affinity mask": "0",
        "max server memory (MB)": "2147483647",
    }
    assert conn.closed is True


def test_sqlserver_driver_resolution_prefers_installed_driver_when_env_not_set(monkeypatch):
    connector = SQLServerConnector(
        host="localhost",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    class _FakePyodbc:
        @staticmethod
        def drivers():
            return ["ODBC Driver 17 for SQL Server", "SQLite3"]

    monkeypatch.delenv("SQLSERVER_ODBC_DRIVER", raising=False)

    assert connector._resolve_driver_name(_FakePyodbc()) == "ODBC Driver 17 for SQL Server"


def test_sqlserver_driver_resolution_prefers_env_override(monkeypatch):
    connector = SQLServerConnector(
        host="localhost",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    class _FakePyodbc:
        @staticmethod
        def drivers():
            return ["ODBC Driver 17 for SQL Server"]

    monkeypatch.setenv("SQLSERVER_ODBC_DRIVER", "{Custom SQL Server Driver}")

    assert connector._resolve_driver_name(_FakePyodbc()) == "Custom SQL Server Driver"
