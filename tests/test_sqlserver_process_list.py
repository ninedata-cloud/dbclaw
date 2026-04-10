import pytest

from backend.services.sqlserver_service import SQLServerConnector, _PROCESS_LIST_SQL


class _FakeCursor:
    def __init__(self):
        self.executed_sql = None
        self.description = [
            ("session_id",),
            ("login_name",),
            ("host_name",),
            ("program_name",),
            ("status",),
            ("cpu_time",),
            ("memory_usage",),
            ("last_request_start_time",),
            ("database_name",),
            ("client_net_address",),
            ("wait_type",),
            ("current_sql",),
        ]

    def execute(self, sql):
        self.executed_sql = sql

    def fetchall(self):
        return [
            (
                51,
                "sa",
                "app-host",
                "app",
                "sleeping",
                12,
                8,
                None,
                "dbguard",
                "10.0.0.8",
                None,
                "SELECT 1",
            )
        ]


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_sqlserver_process_list_query_avoids_invalid_most_recent_dbid():
    conn = _FakeConnection()
    connector = SQLServerConnector(
        host="localhost",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )
    connector._connect = lambda: conn

    result = await connector.get_process_list()

    assert "most_recent_dbid" not in conn.cursor_obj.executed_sql
    assert "sys.sysprocesses" in conn.cursor_obj.executed_sql
    assert "COALESCE(r.database_id, sp.dbid, sql_text.dbid)" in conn.cursor_obj.executed_sql
    assert conn.cursor_obj.executed_sql == _PROCESS_LIST_SQL
    assert conn.closed is True
    assert result == [
        {
            "session_id": 51,
            "login_name": "sa",
            "host_name": "app-host",
            "program_name": "app",
            "status": "sleeping",
            "cpu_time": 12,
            "memory_usage": 8,
            "last_request_start_time": None,
            "database_name": "dbguard",
            "client_net_address": "10.0.0.8",
            "wait_type": None,
            "current_sql": "SELECT 1",
        }
    ]
