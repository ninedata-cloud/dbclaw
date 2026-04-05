import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.datasource import Datasource
from backend.schemas.query import QueryExecuteRequest, QueryExplainRequest
from backend.services.opengauss_service import OpenGaussConnector
from backend.services.oracle_service import OracleConnector
from backend.services.postgres_service import PostgreSQLConnector
from backend.services.mysql_service import MySQLConnector
from backend.services.tidb_service import TiDBConnector
from backend.services.oceanbase_service import OceanBaseConnector
from backend.services.sqlserver_service import SQLServerConnector
from backend.services.dm_service import DMConnector
from backend.utils import db_connector
from backend.routers import query as query_router


class BlankMessageError(Exception):
    pass


def _make_datasource() -> Datasource:
    return Datasource(
        id=1,
        name="test-postgres",
        db_type="postgresql",
        host="localhost",
        port=5432,
        username="tester",
        password_encrypted="encrypted",
        database="dbguard",
    )


@pytest.mark.asyncio
async def test_db_connector_returns_non_empty_error_for_blank_exception_message():
    class FakeConnector:
        def __init__(self, **kwargs):
            pass

        async def execute_query(self, sql: str):
            raise BlankMessageError("")

    datasource = _make_datasource()

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(
            datasource,
            "UPDATE t SET x=1",
            allow_write=True,
        )

    assert result["success"] is False
    assert result["error"]
    assert result["error_type"] == "BlankMessageError"


@pytest.mark.asyncio
async def test_wrapper_adds_success_and_data_for_result_sets():
    class FakeConnector:
        def __init__(self, **kwargs):
            pass

        async def execute_query(self, sql: str):
            return {
                "columns": ["id", "name"],
                "rows": [[1, "alice"]],
                "row_count": 1,
                "execution_time_ms": 12.5,
                "truncated": False,
            }

    datasource = _make_datasource()

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, "SELECT * FROM users")

    assert result["success"] is True
    assert result["data"] == [[1, "alice"]]
    assert result["rows"] == [[1, "alice"]]


@pytest.mark.asyncio
async def test_db_connector_allows_read_only_explain_select_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            pass

        async def execute_query(self, sql: str):
            return {
                "columns": ["QUERY PLAN"],
                "rows": [["Seq Scan on users"]],
                "row_count": 1,
                "execution_time_ms": 3.0,
                "truncated": False,
            }

    datasource = _make_datasource()
    sql = "EXPLAIN SELECT * FROM users"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is True
    assert result["rows"] == [["Seq Scan on users"]]


@pytest.mark.asyncio
async def test_db_connector_rejects_explain_analyze_update_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked EXPLAIN ANALYZE UPDATE")

    datasource = _make_datasource()
    sql = "EXPLAIN ANALYZE UPDATE users SET active = true"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is False
    assert "Only read-only queries" in result["error"]


@pytest.mark.asyncio
async def test_db_connector_rejects_explain_write_forms_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked EXPLAIN write forms")

    datasource = _make_datasource()
    queries = [
        "EXPLAIN DELETE FROM users",
        "EXPLAIN INSERT INTO users (id) VALUES (1)",
        "EXPLAIN MERGE INTO users USING staging_users ON users.id = staging_users.id",
    ]

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        for sql in queries:
            result = await db_connector.execute_query(datasource, sql, allow_write=False)
            assert result["success"] is False
            assert "Only read-only queries" in result["error"]


@pytest.mark.asyncio
async def test_db_connector_allows_read_only_with_select_cte_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            pass

        async def execute_query(self, sql: str):
            return {
                "columns": ["id"],
                "rows": [[1]],
                "row_count": 1,
                "execution_time_ms": 5.0,
                "truncated": False,
            }

    datasource = _make_datasource()
    sql = "WITH recent AS (SELECT id FROM users) SELECT id FROM recent"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is True
    assert result["rows"] == [[1]]


@pytest.mark.asyncio
async def test_db_connector_blocks_write_cte_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked write CTE")

    datasource = _make_datasource()
    sql = "/* leading comment */\nWITH updated AS (UPDATE users SET active = true RETURNING id) SELECT id FROM updated"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is False
    assert "Only read-only queries" in result["error"]


@pytest.mark.asyncio
async def test_db_connector_blocks_exec_and_execute_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked EXEC/EXECUTE")

    datasource = _make_datasource()

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        exec_result = await db_connector.execute_query(datasource, "EXEC sp_who2", allow_write=False)
        execute_result = await db_connector.execute_query(datasource, "EXECUTE sp_who2", allow_write=False)

    assert exec_result["success"] is False
    assert "Only read-only queries" in exec_result["error"]
    assert execute_result["success"] is False
    assert "Only read-only queries" in execute_result["error"]


@pytest.mark.asyncio
async def test_db_connector_blocks_merge_cte_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked MERGE CTE")

    datasource = _make_datasource()
    sql = "WITH merged AS (MERGE INTO users USING staging_users ON users.id = staging_users.id) SELECT 1"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is False
    assert "Only read-only queries" in result["error"]


@pytest.mark.asyncio
async def test_db_connector_rejects_multi_statement_read_only_bypass_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked multi-statement query")

    datasource = _make_datasource()
    sql = "SELECT 1; DELETE FROM users"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is False
    assert "Only read-only queries" in result["error"]


@pytest.mark.asyncio
async def test_db_connector_rejects_multi_statement_selects_when_allow_write_false():
    class FakeConnector:
        def __init__(self, **kwargs):
            raise AssertionError("connector should not be instantiated for blocked multi-statement read-only query")

    datasource = _make_datasource()
    sql = "SELECT 1; SELECT 2"

    with patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakeConnector):
        result = await db_connector.execute_query(datasource, sql, allow_write=False)

    assert result["success"] is False
    assert "Only read-only queries" in result["error"]


@pytest.mark.asyncio
async def test_query_router_consumes_unified_contract_without_breaking_message_and_truncated():
    datasource = _make_datasource()

    class WrappedConnector:
        async def execute_query(self, sql: str, max_rows: int = 1000):
            return await db_connector.execute_query(datasource, sql)

        async def close(self):
            return None

    class FakePostgreSQLConnector:
        def __init__(self, **kwargs):
            pass

        async def execute_query(self, sql: str):
            return {
                "columns": ["id", "payload"],
                "rows": [[1, {"nested": True}]],
                "row_count": 1,
                "execution_time_ms": 8.2,
                "message": "Query executed successfully (1 row, already truncated)",
                "truncated": True,
            }

    async def fake_get_connector_for(datasource_id: int, db):
        return WrappedConnector(), datasource

    req = QueryExecuteRequest(datasource_id=1, sql="SELECT * FROM metrics", max_rows=10)

    with patch("backend.routers.query._get_connector_for", fake_get_connector_for), \
         patch("backend.utils.db_connector.decrypt_value", return_value="secret"), \
         patch("backend.utils.db_connector.PostgreSQLConnector", FakePostgreSQLConnector):
        result = await query_router.execute_query(req, db=None, current_user=MagicMock(id=7))

    assert result.columns == ["id", "payload"]
    assert result.rows == [[1, "{'nested': True}"]]
    assert result.row_count == 1
    assert result.execution_time_ms == 8.2
    assert result.message == "Query executed successfully (1 row, already truncated)"
    assert result.truncated is True


@pytest.mark.asyncio
async def test_query_router_rejects_multi_statement_bypass_before_connector_execution():
    async def fake_get_connector_for(datasource_id: int, db):
        raise AssertionError("connector should not be created for blocked multi-statement query")

    req = QueryExecuteRequest(datasource_id=1, sql="SELECT 1; DROP TABLE users", max_rows=10)

    with patch("backend.routers.query._get_connector_for", fake_get_connector_for):
        with pytest.raises(Exception) as exc_info:
            await query_router.execute_query(req, db=None, current_user=MagicMock(id=7))

    assert exc_info.value.status_code == 400
    assert "Only read-only queries are allowed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_query_router_explain_rejects_write_operation_before_connector_execution():
    async def fake_get_connector_for(datasource_id: int, db):
        raise AssertionError("connector should not be created for blocked explain write query")

    req = QueryExplainRequest(datasource_id=1, sql="EXPLAIN ANALYZE UPDATE users SET active = true")

    with patch("backend.routers.query._get_connector_for", fake_get_connector_for):
        with pytest.raises(Exception) as exc_info:
            await query_router.explain_query(req, db=None)

    assert exc_info.value.status_code == 400
    assert "Only read-only queries can be explained" in exc_info.value.detail




class FakeOracleCursor:
    def __init__(self, description=None, fetch_rows=None, rowcount=0):
        self.description = description
        self._fetch_rows = fetch_rows or []
        self.rowcount = rowcount
        self.execute = AsyncMock()
        self.fetchmany = AsyncMock(return_value=self._fetch_rows)
        self.close = MagicMock()


@pytest.mark.asyncio
async def test_oracle_select_returns_result_set_contract():
    connector = OracleConnector(host="localhost", port=1521, username="tester", password="secret", database="ORCL")
    cursor = FakeOracleCursor(
        description=[("ID",), ("NAME",)],
        fetch_rows=[(1, "alice")],
        rowcount=1,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = AsyncMock()
    conn.close = AsyncMock()

    sql = "SELECT id, name FROM users"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(1001)
    conn.commit.assert_not_called()
    assert result["columns"] == ["ID", "NAME"]
    assert result["rows"] == [[1, "alice"]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    assert "message" not in result
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_select_exact_max_rows_is_not_truncated_without_extra_row():
    connector = OracleConnector(host="localhost", port=1521, username="tester", password="secret", database="ORCL")
    cursor = FakeOracleCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,)],
        rowcount=2,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = AsyncMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = OracleConnector(host="localhost", port=1521, username="tester", password="secret", database="ORCL")
    cursor = FakeOracleCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,), (3,)],
        rowcount=3,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = AsyncMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_execute_query_closes_cursor_on_fetch_failure():
    connector = OracleConnector(host="localhost", port=1521, username="tester", password="secret", database="ORCL")
    cursor = FakeOracleCursor(
        description=[("ID",)],
        rowcount=3,
    )
    cursor.fetchmany = AsyncMock(side_effect=RuntimeError("fetch failed"))
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = AsyncMock()
    conn.close = AsyncMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        with pytest.raises(RuntimeError, match="fetch failed"):
            await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    cursor.close.assert_called_once_with()
    conn.commit.assert_not_called()
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_update_does_not_fetch_without_description():
    connector = OracleConnector(host="localhost", port=1521, username="tester", password="secret", database="ORCL")
    cursor = FakeOracleCursor(description=None, fetch_rows=[(999,)], rowcount=3)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = AsyncMock()
    conn.close = AsyncMock()

    sql = "UPDATE users SET active = 0"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_not_called()
    conn.commit.assert_awaited_once()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 3
    assert result["truncated"] is False
    assert result["message"] == "Statement executed successfully"
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_oracle_plsql_block_without_reliable_rowcount_returns_zero_and_message():
    connector = OracleConnector(host="localhost", port=1521, username="tester", password="secret", database="ORCL")
    cursor = FakeOracleCursor(description=None, rowcount=-1)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = AsyncMock()
    conn.close = AsyncMock()

    sql = "BEGIN NULL; END;"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_not_called()
    conn.commit.assert_awaited_once()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 0
    assert result["truncated"] is False
    assert result["message"] == "Statement executed successfully"
    conn.close.assert_awaited_once()

class FakeRecord:
    def __init__(self, data):
        self._data = data

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()


class SyncCursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAioMysqlCursor:
    def __init__(self, description=None, fetch_rows=None, rowcount=0):
        self.description = description
        self._fetch_rows = fetch_rows or []
        self.rowcount = rowcount
        self.execute = AsyncMock()
        self.fetchmany = AsyncMock(return_value=self._fetch_rows)


class FakeSyncCursor:
    def __init__(self, description=None, fetch_rows=None, rowcount=0):
        self.description = description
        self._fetch_rows = fetch_rows or []
        self.rowcount = rowcount
        self.execute = MagicMock()
        self.fetchmany = MagicMock(return_value=self._fetch_rows)
        self.close = MagicMock()


@pytest.mark.asyncio
async def test_mysql_update_returns_no_result_set_contract_with_message_and_truncated_false_and_commits():
    connector = MySQLConnector(host="localhost", port=3306, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(description=None, rowcount=3)
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.commit = AsyncMock()
    conn.close = MagicMock()

    sql = "UPDATE users SET active = 0"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_not_called()
    conn.commit.assert_awaited_once()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 3
    assert result["truncated"] is False
    assert result["message"] == "Query OK, 3 rows affected"
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_mysql_select_exact_max_rows_is_not_truncated_without_extra_row():
    connector = MySQLConnector(host="localhost", port=3306, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(
        description=[("ID",), ("NAME",)],
        fetch_rows=[(1, "alice"), (2, "bob")],
        rowcount=2,
    )
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.close = MagicMock()

    sql = "SELECT id, name FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID", "NAME"]
    assert result["rows"] == [[1, "alice"], [2, "bob"]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_mysql_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = MySQLConnector(host="localhost", port=3306, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,), (3,)],
        rowcount=3,
    )
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.close = MagicMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_tidb_update_returns_no_result_set_contract_with_message_and_truncated_false_and_commits():
    connector = TiDBConnector(host="localhost", port=4000, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(description=None, rowcount=2)
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.commit = AsyncMock()
    conn.close = MagicMock()

    sql = "UPDATE users SET active = 1"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_not_called()
    conn.commit.assert_awaited_once()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 2
    assert result["truncated"] is False
    assert result["message"] == "Query OK, 2 rows affected"
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_tidb_select_exact_max_rows_is_not_truncated_without_extra_row():
    connector = TiDBConnector(host="localhost", port=4000, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(
        description=[("ID",), ("NAME",)],
        fetch_rows=[(1, "alice"), (2, "bob")],
        rowcount=2,
    )
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.close = MagicMock()

    sql = "SELECT id, name FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID", "NAME"]
    assert result["rows"] == [[1, "alice"], [2, "bob"]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_tidb_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = TiDBConnector(host="localhost", port=4000, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,), (3,)],
        rowcount=3,
    )
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.close = MagicMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_oceanbase_update_returns_no_result_set_contract_with_message_and_truncated_false_and_commits():
    connector = OceanBaseConnector(host="localhost", port=2881, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(description=None, rowcount=4)
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.commit = AsyncMock()
    conn.close = MagicMock()

    sql = "DELETE FROM users WHERE inactive = 1"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_not_called()
    conn.commit.assert_awaited_once()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 4
    assert result["truncated"] is False
    assert result["message"] == "Query OK, 4 rows affected"
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_oceanbase_select_exact_max_rows_is_not_truncated_without_extra_row():
    connector = OceanBaseConnector(host="localhost", port=2881, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(
        description=[("ID",), ("NAME",)],
        fetch_rows=[(1, "alice"), (2, "bob")],
        rowcount=2,
    )
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.close = MagicMock()

    sql = "SELECT id, name FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID", "NAME"]
    assert result["rows"] == [[1, "alice"], [2, "bob"]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_oceanbase_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = OceanBaseConnector(host="localhost", port=2881, username="tester", password="secret", database="dbguard")
    cursor = FakeAioMysqlCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,), (3,)],
        rowcount=3,
    )
    conn = MagicMock()
    conn.cursor.return_value = SyncCursorContext(cursor)
    conn.close = MagicMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_awaited_once_with(sql)
    cursor.fetchmany.assert_awaited_once_with(3)
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_sqlserver_update_returns_unified_no_result_set_contract():
    connector = SQLServerConnector(host="localhost", port=1433, username="tester", password="secret", database="dbguard")
    cursor = FakeSyncCursor(description=None, rowcount=5)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = MagicMock()

    sql = "UPDATE users SET active = 0"
    with patch.object(connector, "_connect", MagicMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_called_once_with(sql)
    cursor.fetchmany.assert_not_called()
    cursor.close.assert_called_once_with()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 5
    assert result["truncated"] is False
    assert result["message"] == "Query OK, 5 rows affected"
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_called_once_with()




@pytest.mark.asyncio
async def test_sqlserver_select_exact_max_rows_is_not_truncated_without_extra_row():
    connector = SQLServerConnector(host="localhost", port=1433, username="tester", password="secret", database="dbguard")
    cursor = FakeSyncCursor(
        description=[("ID",), ("NAME",)],
        fetch_rows=[(1, "alice"), (2, "bob")],
        rowcount=2,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = MagicMock()

    sql = "SELECT id, name FROM users ORDER BY id"
    with patch.object(connector, "_connect", MagicMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_called_once_with(sql)
    cursor.fetchmany.assert_called_once_with(3)
    cursor.close.assert_called_once_with()
    assert result["columns"] == ["ID", "NAME"]
    assert result["rows"] == [[1, "alice"], [2, "bob"]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_sqlserver_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = SQLServerConnector(host="localhost", port=1433, username="tester", password="secret", database="dbguard")
    cursor = FakeSyncCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,), (3,)],
        rowcount=3,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = MagicMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", MagicMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_called_once_with(sql)
    cursor.fetchmany.assert_called_once_with(3)
    cursor.close.assert_called_once_with()
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_dm_plsql_returns_unified_no_result_set_contract_when_rowcount_unreliable_and_commits():
    connector = DMConnector(host="localhost", port=5236, username="tester", password="secret", database="dbguard")
    cursor = FakeSyncCursor(description=None, rowcount=-1)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = MagicMock()
    conn.close = MagicMock()

    sql = "BEGIN NULL; END;"
    with patch.object(connector, "_connect", MagicMock(return_value=conn)):
        result = await connector.execute_query(sql)

    cursor.execute.assert_called_once_with(sql)
    cursor.fetchmany.assert_not_called()
    conn.commit.assert_called_once_with()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 0
    assert result["truncated"] is False
    assert result["message"] == "Query OK, 0 rows affected"
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_dm_select_exact_max_rows_is_not_truncated_without_extra_row():
    connector = DMConnector(host="localhost", port=5236, username="tester", password="secret", database="dbguard")
    cursor = FakeSyncCursor(
        description=[("ID",), ("NAME",)],
        fetch_rows=[(1, "alice"), (2, "bob")],
        rowcount=2,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = MagicMock()

    sql = "SELECT id, name FROM users ORDER BY id"
    with patch.object(connector, "_connect", MagicMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_called_once_with(sql)
    cursor.fetchmany.assert_called_once_with(3)
    assert result["columns"] == ["ID", "NAME"]
    assert result["rows"] == [[1, "alice"], [2, "bob"]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_dm_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = DMConnector(host="localhost", port=5236, username="tester", password="secret", database="dbguard")
    cursor = FakeSyncCursor(
        description=[("ID",)],
        fetch_rows=[(1,), (2,), (3,)],
        rowcount=3,
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = MagicMock()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", MagicMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    cursor.execute.assert_called_once_with(sql)
    cursor.fetchmany.assert_called_once_with(3)
    assert result["columns"] == ["ID"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_called_once_with()


class FakeAsyncContextManager:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAttribute:
    def __init__(self, name):
        self.name = name


def _prepared_statement(column_names=None, rows=None):
    prepared = MagicMock()
    prepared.get_attributes.return_value = [FakeAttribute(name) for name in (column_names or [])]
    prepared.fetch = AsyncMock(return_value=rows or [])
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows or [])
    prepared.cursor.return_value = cursor
    return prepared


@pytest.mark.asyncio
async def test_postgres_select_returns_result_set_contract():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1, "name": "alice"})]
    prepared = _prepared_statement(["id", "name"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()
    sql = "SELECT id, name FROM users"

    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [[1, "alice"]]
    assert result["row_count"] == 1
    assert "message" not in result
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_update_returns_no_result_set_contract():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "UPDATE 3"

    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query("UPDATE users SET active = false")

    conn.prepare.assert_awaited_once_with("UPDATE users SET active = false")
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    conn.execute.assert_awaited_once_with("UPDATE users SET active = false")
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 3
    assert result["truncated"] is False
    assert result["message"] == "UPDATE 3"
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_create_table_without_numeric_count_returns_zero_row_count():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "CREATE TABLE"

    sql = "CREATE TABLE users (id INT)"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    conn.execute.assert_awaited_once_with(sql)
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 0
    assert result["truncated"] is False
    assert result["message"] == "CREATE TABLE"
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_insert_returning_still_uses_bounded_cursor_fetch():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 42})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "INSERT INTO users(name) VALUES ('alice') RETURNING id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[42]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_select_exact_max_rows_is_not_truncated_without_fetching_all_rows():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1}), FakeRecord({"id": 2})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(3)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1}), FakeRecord({"id": 2}), FakeRecord({"id": 3})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(3)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_with_update_without_returning_uses_execute():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "UPDATE 5"

    sql = "/* leading comment */\nWITH updated AS (UPDATE users SET active = true) UPDATE users SET seen_at = now()"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.execute.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 5


@pytest.mark.asyncio
async def test_postgres_with_nested_returning_but_top_level_update_uses_execute():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "UPDATE 2"

    sql = (
        "WITH moved AS ("
        "DELETE FROM users WHERE inactive = true RETURNING id"
        ") "
        "UPDATE accounts SET archived_user_count = archived_user_count + 1"
    )
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.execute.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 2
    assert result["message"] == "UPDATE 2"
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_with_materialized_cte_select_uses_bounded_cursor_fetch():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "WITH recent AS MATERIALIZED (SELECT id FROM users) SELECT id FROM recent"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[1]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_with_not_materialized_cte_select_uses_bounded_cursor_fetch():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 2})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "WITH recent AS NOT MATERIALIZED (SELECT id FROM users) SELECT id FROM recent"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[2]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_explain_analyze_uses_bounded_cursor_fetch_via_prepared_metadata():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"QUERY PLAN": "Seq Scan on users"})]
    prepared = _prepared_statement(["QUERY PLAN"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "EXPLAIN ANALYZE SELECT * FROM users"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["QUERY PLAN"]
    assert result["rows"] == [["Seq Scan on users"]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_connect_retries_after_timeout():
    connector = PostgreSQLConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    successful_connection = object()
    connect_mock = AsyncMock(side_effect=[TimeoutError("first timeout"), successful_connection])

    asyncpg_module = MagicMock()
    asyncpg_module.connect = connect_mock

    with patch.dict("sys.modules", {"asyncpg": asyncpg_module}):
        result = await connector._connect()

    assert result is successful_connection
    assert connect_mock.await_count == 2


@pytest.mark.asyncio
async def test_opengauss_select_returns_result_set_contract():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1, "name": "alice"})]
    prepared = _prepared_statement(["id", "name"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "SELECT id, name FROM users"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [[1, "alice"]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    assert "message" not in result
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_ddl_returns_no_result_set_contract():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "CREATE TABLE"

    sql = "CREATE TABLE users (id INT)"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    conn.execute.assert_awaited_once_with(sql)
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 0
    assert result["truncated"] is False
    assert result["message"] == "CREATE TABLE"
    assert isinstance(result["execution_time_ms"], float)
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_insert_returning_uses_bounded_cursor_fetch_via_prepared_metadata():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 42})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "INSERT INTO users(name) VALUES ('alice') RETURNING id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(1001)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[42]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_select_exact_max_rows_is_not_truncated_without_fetching_all_rows():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1}), FakeRecord({"id": 2})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(3)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_select_more_than_max_rows_is_truncated_to_visible_rows():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"id": 1}), FakeRecord({"id": 2}), FakeRecord({"id": 3})]
    prepared = _prepared_statement(["id"], rows)
    cursor = AsyncMock()
    cursor.fetch = AsyncMock(return_value=rows)
    conn.prepare.return_value = prepared
    conn.cursor.return_value = cursor
    conn.transaction.return_value = FakeAsyncContextManager()

    sql = "SELECT id FROM users ORDER BY id"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql, max_rows=2)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    conn.cursor.assert_called_once_with(sql)
    cursor.fetch.assert_awaited_once_with(3)
    conn.transaction.assert_called_once_with()
    prepared.cursor.assert_not_called()
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["id"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_explain_analyze_uses_fetch_via_prepared_metadata():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    rows = [FakeRecord({"QUERY PLAN": "Seq Scan on users"})]
    prepared = _prepared_statement(["QUERY PLAN"], rows)
    conn.prepare.return_value = prepared

    sql = "EXPLAIN ANALYZE SELECT * FROM users"
    conn.fetch.return_value = rows
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    conn.fetch.assert_awaited_once_with(sql)
    prepared.cursor.assert_not_called()
    conn.execute.assert_not_called()
    assert result["columns"] == ["QUERY PLAN"]
    assert result["rows"] == [["Seq Scan on users"]]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_with_delete_without_returning_uses_execute():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "DELETE 7"

    sql = "WITH deleted AS (DELETE FROM users WHERE inactive = true) DELETE FROM audit_log WHERE user_id IS NULL"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    conn.execute.assert_awaited_once_with(sql)
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 7
    assert result["truncated"] is False
    assert result["message"] == "DELETE 7"
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_with_top_level_write_without_returning_uses_execute():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "UPDATE 5"

    sql = "/* leading comment */\nWITH updated AS (UPDATE users SET active = true) UPDATE users SET seen_at = now()"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    conn.execute.assert_awaited_once_with(sql)
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 5
    assert result["truncated"] is False
    assert result["message"] == "UPDATE 5"
    conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_opengauss_insert_command_tag_with_multiple_numbers_uses_last_number_as_row_count():
    connector = OpenGaussConnector(host="localhost", port=5432, username="tester", password="secret", database="dbguard")
    conn = AsyncMock()
    prepared = _prepared_statement()
    conn.prepare.return_value = prepared
    conn.execute.return_value = "INSERT 0 1"

    sql = "INSERT INTO users(name) VALUES ('alice')"
    with patch.object(connector, "_connect", AsyncMock(return_value=conn)):
        result = await connector.execute_query(sql)

    conn.prepare.assert_awaited_once_with(sql)
    prepared.fetch.assert_not_called()
    prepared.cursor.assert_not_called()
    conn.execute.assert_awaited_once_with(sql)
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["row_count"] == 1
    assert result["truncated"] is False
    assert result["message"] == "INSERT 0 1"
    conn.close.assert_awaited_once()
