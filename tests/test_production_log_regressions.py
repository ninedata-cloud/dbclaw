import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.config import Settings
from backend.migrations.ensure_timescale import _is_postgres_url
from backend.services import host_collector, metric_collector, startup_self_check, weixin_bot_service
from backend.services.mysql_service import MySQLConnector
from backend.services.ssh_connection_pool import SSHConnectionPool
from backend.models.integration_bot_binding import IntegrationBotBinding


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _SessionContext:
    def __init__(self, session, events=None, label=None):
        self.session = session
        self.events = events
        self.label = label

    async def __aenter__(self):
        if self.events is not None:
            self.events.append(f"{self.label}_enter")
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        if self.events is not None:
            self.events.append(f"{self.label}_exit")
        return False


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.unit
def test_default_pool_and_collection_capacity_are_tripled():
    settings = Settings(_env_file=None)

    assert settings.database_pool_size == 30
    assert settings.database_max_overflow == 60
    assert settings.datasource_collection_concurrency == 24
    assert settings.host_collection_concurrency == 15
    assert settings.integration_collection_concurrency == 12
    assert settings.metadata_write_concurrency == 9


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@db:5432/app",
        "postgresql+psycopg://u:p@db:5432/app",
        "postgresql://u:p@db:5432/app",
        "postgres://u:p@db:5432/app",
    ],
)
def test_timescale_recognizes_postgres_backends(url):
    assert _is_postgres_url(url)


@pytest.mark.unit
def test_timescale_rejects_non_postgres_backend():
    assert not _is_postgres_url("mysql+aiomysql://u:p@db:3306/app")


@pytest.mark.unit
def test_database_pool_uses_configured_limits(mocker):
    from backend import database

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://u:p@db:5432/app",
        debug=False,
        database_pool_size=7,
        database_max_overflow=9,
        database_pool_timeout_seconds=4.5,
        database_pool_recycle_seconds=900,
    )
    mocker.patch.object(database, "get_settings", return_value=settings)
    create = mocker.patch.object(database, "create_async_engine", return_value=object())

    database._create_engine()

    assert create.call_args.kwargs["pool_size"] == 7
    assert create.call_args.kwargs["max_overflow"] == 9
    assert create.call_args.kwargs["pool_timeout"] == 4.5
    assert create.call_args.kwargs["pool_recycle"] == 900


@pytest.mark.service
@pytest.mark.asyncio
async def test_datasource_remote_io_starts_after_load_session_closes(mocker):
    events = []
    datasource = SimpleNamespace(
        id=1,
        is_active=True,
        metric_source="system",
        silence_until=None,
        silence_reason=None,
        host_id=None,
        db_type="mysql",
        host="db",
        port=3306,
        username="u",
        password_encrypted=None,
        database="app",
        extra_params={},
        connection_status="unknown",
        connection_error=None,
        connection_checked_at=None,
    )
    load_db = AsyncMock()
    load_db.execute = AsyncMock(return_value=_ScalarResult(datasource))
    persist_db = AsyncMock()
    persist_db.execute = AsyncMock(return_value=_ScalarResult(datasource))
    persist_db.add = Mock()

    contexts = iter(
        [
            _SessionContext(load_db, events, "load"),
            _SessionContext(persist_db, events, "persist"),
        ]
    )
    mocker.patch.object(metric_collector, "async_session", side_effect=lambda: next(contexts))

    connector = SimpleNamespace()

    async def _get_status():
        events.append("remote_start")
        assert "load_exit" in events
        return {"Threads_connected": 1, "Threads_running": 0}

    connector.get_status = _get_status
    connector.close = AsyncMock()
    connector.test_connection = AsyncMock(return_value="ok")
    mocker.patch.object(metric_collector, "get_connector", return_value=connector)
    mocker.patch(
        "backend.services.metric_normalizer.MetricNormalizer.normalize",
        return_value={"connections_total": 1},
    )
    mocker.patch.object(metric_collector, "_auto_resolve_connection_alerts", AsyncMock())
    mocker.patch.object(metric_collector, "_route_alert_engine", AsyncMock())
    mocker.patch.object(metric_collector, "_push_to_subscribers", AsyncMock())

    await metric_collector.collect_metrics_for_connection(1)

    assert events.index("load_exit") < events.index("remote_start") < events.index("persist_enter")
    connector.close.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_datasource_collection_concurrency_is_bounded(mocker):
    active = 0
    peak = 0

    async def _slow_load(_datasource_id):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return None

    mocker.patch.object(metric_collector, "_load_collection_config", side_effect=_slow_load)
    count = metric_collector._settings.datasource_collection_concurrency * 3

    await asyncio.gather(
        *(metric_collector.collect_metrics_for_connection(index) for index in range(count))
    )

    assert peak <= metric_collector._settings.datasource_collection_concurrency


@pytest.mark.unit
def test_ssh_failures_enable_retry_backoff():
    pool = SSHConnectionPool()
    pool._record_connection_failure(55, "unreachable")

    with pytest.raises(ConnectionError, match="retry backoff active"):
        pool._check_retry_backoff(55)

    assert pool.get_stats()["backoff_hosts"] == 1


@pytest.mark.unit
def test_host_collection_overrun_never_hot_loops():
    assert host_collector._compute_round_sleep(60, 120) >= 0.1
    assert host_collector._compute_round_sleep(60, 10) == 50


@pytest.mark.service
@pytest.mark.asyncio
async def test_host_ssh_collection_finishes_before_persistence_session_opens(mocker):
    events = []
    host = SimpleNamespace(id=12, name="db-host")
    save_db = AsyncMock()
    save_db.execute = AsyncMock(return_value=_ScalarResult(None))
    save_db.add = Mock()
    mocker.patch.object(
        host_collector,
        "async_session",
        return_value=_SessionContext(save_db, events, "save"),
    )

    class _Pool:
        @asynccontextmanager
        async def get_collector_connection(self, _host):
            yield object()

    mocker.patch(
        "backend.services.ssh_connection_pool.get_ssh_pool",
        return_value=_Pool(),
    )

    async def _collect(*_args, **_kwargs):
        events.append("ssh_collect")
        assert "save_enter" not in events
        return {"cpu_usage": 1, "memory_usage": 2, "disk_usage": 3}

    mocker.patch(
        "backend.services.os_metrics_collector.OSMetricsCollector.collect_via_ssh",
        side_effect=_collect,
    )

    await host_collector._collect_host_metric(host)

    assert events.index("ssh_collect") < events.index("save_enter")
    save_db.commit.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_weixin_long_poll_finishes_before_cursor_db_session_opens(mocker):
    events = []
    binding = SimpleNamespace(
        id=9,
        params={
            "api_baseurl": "https://weixin.example",
            "bot_token": "token",
            "login_status": "confirmed",
            "get_updates_buf": "old",
        },
    )
    stored = IntegrationBotBinding(
        id=9,
        integration_id=1,
        code="weixin_bot",
        name="Weixin",
        is_enabled=True,
        params=dict(binding.params),
    )
    save_db = AsyncMock()
    save_db.execute = AsyncMock(return_value=_ScalarResult(stored))
    mocker.patch.object(
        weixin_bot_service,
        "async_session",
        return_value=_SessionContext(save_db, events, "save"),
    )

    async def _get_updates(**_kwargs):
        events.append("remote_start")
        await asyncio.sleep(0)
        events.append("remote_end")
        return {"msgs": [], "get_updates_buf": "new"}

    mocker.patch.object(weixin_bot_service.weixin_service, "get_updates", side_effect=_get_updates)

    await weixin_bot_service.WeixinBotService.poll_once(None, binding)

    assert events.index("remote_end") < events.index("save_enter")
    assert stored.params["get_updates_buf"] == "new"
    save_db.commit.assert_awaited_once()


class _MySQLStatusCursor:
    def __init__(self):
        self.executed = []
        self.current = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=None):
        self.current = sql
        self.executed.append(sql)

    async def fetchall(self):
        if self.current == "SHOW GLOBAL STATUS":
            return [
                ("Uptime", "100"),
                ("Threads_connected", "3"),
                ("Threads_running", "0"),
            ]
        return []

    async def fetchone(self):
        if self.current == "SHOW GLOBAL VARIABLES LIKE 'max_connections'":
            return ("max_connections", "200")
        return None


class _MySQLStatusConnection:
    def __init__(self):
        self.status_cursor = _MySQLStatusCursor()
        self.closed = False

    def cursor(self, *_args, **_kwargs):
        return self.status_cursor

    def close(self):
        self.closed = True


@pytest.mark.service
@pytest.mark.asyncio
async def test_mysql_status_avoids_deprecated_processlist_when_global_status_has_keys(mocker):
    connection = _MySQLStatusConnection()
    connector = MySQLConnector("db", 3306, "u", "p", "app", db_type="mysql")
    mocker.patch.object(connector, "_connect", AsyncMock(return_value=connection))

    status = await connector.get_status()

    assert status["connections_total"] == 3
    assert status["connections_active"] == 0
    assert status["process_count"] == 3
    assert not any("PROCESSLIST" in sql.upper() for sql in connection.status_cursor.executed)


@pytest.mark.service
@pytest.mark.asyncio
async def test_readiness_uses_the_application_engine(mocker):
    shared_engine = object()
    expected = startup_self_check.CheckResult(
        name="Metadata database",
        status="pass",
        severity="info",
        summary="ok",
    )
    mocker.patch.object(startup_self_check, "_check_runtime_paths", return_value=[])
    check = mocker.patch.object(
        startup_self_check,
        "_check_metadata_database",
        AsyncMock(return_value=expected),
    )
    mocker.patch("backend.database.get_engine", return_value=shared_engine)

    report = await startup_self_check.run_readiness_self_check(Settings())

    assert report.ok
    assert check.await_args.kwargs["shared_engine"] is shared_engine


@pytest.mark.unit
def test_container_bootstrap_never_logs_plaintext_default_credentials():
    entrypoint = (PROJECT_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "Default admin credentials" not in entrypoint
    assert 'INITIAL_ADMIN_PASSWORD="$(generate_password)"' in entrypoint


@pytest.mark.unit
def test_supervisord_activity_log_does_not_duplicate_stdout():
    config = (PROJECT_ROOT / "docker" / "supervisord.conf").read_text(encoding="utf-8")

    assert "logfile=/dev/null" in config
    assert "\nlogfile=/dev/fd/1\n" not in config
