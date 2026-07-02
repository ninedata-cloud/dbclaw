from types import SimpleNamespace

import pytest

from backend.agent.skill_selector import skill_matches_datasource
from backend.routers import query as query_router
from backend.schemas.datasource import DatasourceCreate, DatasourceTestRequest
from backend.services.connection_diagnostic_service import ConnectionDiagnosticService
from backend.services.datasource_metric_merge import cleanup_obsolete_integration_keys
from backend.services.db_connector import get_connector
from backend.services.db_types import compatibility_db_types, is_mysql_family, normalize_db_type
from backend.services.metric_normalizer import MetricNormalizer
from backend.services.mysql_service import MySQLConnector
from backend.utils.version_parser import simplify_version


@pytest.mark.unit
def test_oceanbase_mysql_is_supported_as_mysql_family():
    assert normalize_db_type("oceanbase_mysql") == "oceanbase-mysql"
    assert is_mysql_family("oceanbase-mysql")
    assert compatibility_db_types("oceanbase-mysql") == [
        "oceanbase-mysql",
        "oceanbase",
        "mysql",
        "general",
    ]


@pytest.mark.unit
def test_datasource_schemas_accept_oceanbase_mysql():
    created = DatasourceCreate(
        name="ob-prod",
        db_type="oceanbase-mysql",
        host="127.0.0.1",
        port=2883,
    )
    test_req = DatasourceTestRequest(
        db_type="oceanbase-mysql",
        host="127.0.0.1",
        port=2883,
    )

    assert created.db_type == "oceanbase-mysql"
    assert test_req.db_type == "oceanbase-mysql"


@pytest.mark.unit
def test_oceanbase_mysql_uses_mysql_connector_and_query_database_selector():
    connector = get_connector("oceanbase-mysql", "127.0.0.1", 2883)
    assert isinstance(connector, MySQLConnector)
    assert "oceanbase-mysql" in query_router._DB_TYPES_WITH_DATABASE_LIST_FROM_SCHEMAS


@pytest.mark.unit
def test_connection_diagnostic_accepts_oceanbase_mysql():
    service = ConnectionDiagnosticService(db=None)
    assert service._validate_config("oceanbase-mysql", "127.0.0.1", 2883) is None


@pytest.mark.unit
def test_oceanbase_mysql_metric_normalizer_reuses_mysql_rules(mocker):
    mocker.patch.object(MetricNormalizer, "_calculate_rate", return_value=12.5)
    normalized = MetricNormalizer.normalize(
        "oceanbase-mysql",
        9001,
        {
            "questions": 1000,
            "com_commit": 30,
            "com_rollback": 2,
            "cache_hit_rate": 99.1,
            "innodb_data_reads": 44,
        },
    )

    assert normalized["qps"] == 12.5
    assert normalized["tps"] == 12.5
    assert normalized["cache_hit_rate"] == 99.1
    assert normalized["disk_reads_per_sec"] == 12.5


@pytest.mark.unit
def test_oceanbase_mysql_reuses_mysql_skills_and_metric_cleanup():
    skill = SimpleNamespace(id="mysql_get_db_status", category="mysql", tags=["mysql"])

    assert skill_matches_datasource(skill, "oceanbase-mysql")
    cleaned = cleanup_obsolete_integration_keys(
        "oceanbase-mysql",
        {"connections_active": 1, "active_connections": 2},
    )
    assert "active_connections" not in cleaned


@pytest.mark.unit
def test_simplify_version_formats_oceanbase_mysql():
    result = simplify_version("5.7.25-OceanBase-v4.3.0", "oceanbase-mysql")
    assert result["short"] == "OceanBase MySQL 5.7.25"


class _FakeCursor:
    def __init__(self, audit_view="GV$OB_SQL_AUDIT"):
        self._fetchone = None
        self._fetchall = []
        self.description = []
        self.audit_view = audit_view
        self.executed_sql = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        if sql == "SHOW GLOBAL STATUS":
            raise RuntimeError("SHOW GLOBAL STATUS not supported")
        if "FROM information_schema.PROCESSLIST" in sql:
            self._fetchone = (4, 2)
            return
        if sql == "SHOW GLOBAL VARIABLES LIKE 'max_connections'":
            self._fetchone = ("max_connections", "100")
            return
        if sql == "SHOW VARIABLES LIKE 'performance_schema'":
            self._fetchone = ("performance_schema", "OFF")
            return
        if "information_schema.COLUMNS" in sql and params:
            table_name = params[0]
            if table_name != self.audit_view:
                self._fetchall = []
                return
            self._fetchall = [
                ("QUERY_SQL",),
                ("SQL_ID",),
                ("ELAPSED_TIME",),
                ("MEMSTORE_READ_ROW_COUNT",),
                ("SSSTORE_READ_ROW_COUNT",),
                ("TOTAL_WAIT_TIME_MICRO",),
                ("REQUEST_TIME",),
                ("IS_INNER_SQL",),
                ("IS_EXECUTOR_RPC",),
            ]
            return
        if f"`oceanbase`.`{self.audit_view}`" in sql:
            self._fetchall = [
                (
                    "select 1",
                    "sql-1",
                    3,
                    1.5,
                    12,
                    0.3,
                    0.5,
                    4.0,
                    0.1,
                    "2026-07-02 10:00:00",
                ),
            ]
            return
        raise RuntimeError(f"unexpected SQL: {sql}")

    async def fetchone(self):
        return self._fetchone

    async def fetchall(self):
        return self._fetchall


class _FakeConnection:
    def __init__(self, audit_view="GV$OB_SQL_AUDIT"):
        self.closed = False
        self.audit_view = audit_view
        self.cursors = []

    def cursor(self, *args, **kwargs):
        cursor = _FakeCursor(self.audit_view)
        self.cursors.append(cursor)
        return cursor

    def close(self):
        self.closed = True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mysql_connector_status_degrades_when_global_status_missing(mocker):
    connector = MySQLConnector("127.0.0.1", 2883)
    fake_conn = _FakeConnection()
    mocker.patch.object(connector, "_connect", return_value=fake_conn)

    status = await connector.get_status()

    assert status["connections_total"] == 4
    assert status["connections_active"] == 2
    assert status["max_connections"] == 100
    assert status["questions"] == 0
    assert fake_conn.closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mysql_connector_top_sql_falls_back_to_oceanbase_audit(mocker):
    connector = MySQLConnector("127.0.0.1", 2883, db_type="oceanbase-mysql")
    fake_conn = _FakeConnection()
    mocker.patch.object(connector, "_connect", return_value=fake_conn)

    rows = await connector.get_top_sql(limit=10)

    assert rows[0]["sql_text"] == "select 1"
    assert rows[0]["sql_id"] == "sql-1"
    assert rows[0]["exec_count"] == 3
    assert rows[0]["total_rows_scanned"] == 12
    assert rows[0]["total_wait_time_sec"] == 0.3
    executed = "\n".join(sql for cursor in fake_conn.cursors for sql in cursor.executed_sql)
    assert "`oceanbase`.`GV$OB_SQL_AUDIT`" in executed
    assert "FROM GV$OB_SQL_AUDIT" not in executed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mysql_connector_top_sql_supports_oceanbase_3_sql_audit_view(mocker):
    connector = MySQLConnector("127.0.0.1", 2883, db_type="oceanbase-mysql")
    fake_conn = _FakeConnection(audit_view="GV$SQL_AUDIT")
    mocker.patch.object(connector, "_connect", return_value=fake_conn)

    rows = await connector.get_top_sql(limit=10)

    assert rows[0]["sql_text"] == "select 1"
    assert rows[0]["sql_id"] == "sql-1"
    executed = "\n".join(sql for cursor in fake_conn.cursors for sql in cursor.executed_sql)
    assert "`oceanbase`.`GV$OB_SQL_AUDIT`" in executed
    assert "`oceanbase`.`GV$SQL_AUDIT`" in executed
