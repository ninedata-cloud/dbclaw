from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import integration_scheduler as scheduler_service


class _AsyncSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsAllResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return SimpleNamespace(all=lambda: self._values)


def _datasource():
    return SimpleNamespace(
        id=7,
        name="prod-mysql",
        is_active=True,
        metric_source="integration",
        inbound_source={
            "integration_id": 101,
            "enabled": True,
            "params": {"region": "cn-hangzhou"},
        },
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database="app",
        external_instance_id="rm-001",
        username="u",
        password_encrypted=None,
        extra_params={},
    )


def _integration():
    return SimpleNamespace(
        id=101,
        is_enabled=True,
        integration_type="inbound_metric",
        code="collect_metrics()",
        last_run_at=None,
        last_error="old error",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_integration_collects_merges_persists_and_pushes(mocker):
    datasource = _datasource()
    integration = _integration()
    latest_snapshot = SimpleNamespace(
        data={
            "cpu_usage": 10.0,
            "foo": "direct-value",
            "uptime": 1,
            "active_connections": 99,
        }
    )
    session = AsyncMock()
    added = []
    session.add = lambda obj: added.append(obj)
    session.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(latest_snapshot))
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(session))
    mocker.patch.object(
        scheduler_service,
        "get_alive_by_id",
        AsyncMock(side_effect=[datasource, integration]),
    )
    executor = SimpleNamespace(
        execute_metric_collection=AsyncMock(
            return_value=[
                {"datasource_id": 7, "metric_name": "cpu_usage", "metric_value": 88.0},
                {"datasource_id": 7, "metric_name": "qps", "metric_value": 123.0},
                {"datasource_id": 7, "metric_name": "connections_active", "metric_value": 5},
                {"datasource_id": 7, "metric_name": "foo", "metric_value": "integration-ignored"},
                {"datasource_id": 8, "metric_name": "cpu_usage", "metric_value": 99.0},
                {"datasource_id": 7, "metric_name": "missing_value"},
            ]
        )
    )
    mocker.patch("backend.services.integration_scheduler.IntegrationExecutor", return_value=executor)
    mocker.patch.object(
        scheduler_service,
        "_collect_direct_metrics_supplement",
        AsyncMock(return_value={"uptime": 3600, "cache_hit_rate": 0.97}),
    )
    push = mocker.patch.object(scheduler_service, "_push_to_subscribers", AsyncMock())

    await scheduler_service.execute_integration(7)

    assert len(added) == 2
    execution_log, snapshot = added
    assert execution_log.status == "success"
    assert execution_log.result == {"datasource_count": 1, "metric_count": 6}
    assert execution_log.payload_summary == {"datasource_id": 7}
    assert integration.last_error is None
    assert integration.last_run_at is not None
    assert snapshot.datasource_id == 7
    assert snapshot.metric_type == "db_status"
    assert snapshot.data["cpu_usage"] == 88.0
    assert snapshot.data["qps"] == 123.0
    assert snapshot.data["connections_active"] == 5
    assert snapshot.data["foo"] == "direct-value"
    assert snapshot.data["uptime"] == 3600
    assert snapshot.data["cache_hit_rate"] == 0.97
    assert "active_connections" not in snapshot.data
    push.assert_awaited_once()
    pushed_datasource_id, pushed_payload = push.await_args.args
    assert pushed_datasource_id == 7
    assert pushed_payload["type"] == "db_status"
    assert pushed_payload["data"] == snapshot.data
    assert session.commit.await_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_integration_records_failure_when_executor_raises(mocker):
    datasource = _datasource()
    integration = _integration()
    session = AsyncMock()
    added = []
    session.add = lambda obj: added.append(obj)
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(session))
    mocker.patch.object(
        scheduler_service,
        "get_alive_by_id",
        AsyncMock(side_effect=[datasource, integration]),
    )
    executor = SimpleNamespace(
        execute_metric_collection=AsyncMock(side_effect=RuntimeError("provider timeout"))
    )
    mocker.patch("backend.services.integration_scheduler.IntegrationExecutor", return_value=executor)
    push = mocker.patch.object(scheduler_service, "_push_to_subscribers", AsyncMock())

    await scheduler_service.execute_integration(7)

    assert len(added) == 1
    execution_log = added[0]
    assert execution_log.status == "failed"
    assert "provider timeout" in execution_log.error_message
    assert "provider timeout" in integration.last_error
    assert integration.last_run_at is not None
    push.assert_not_awaited()
    assert session.commit.await_count == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_integration_records_success_without_snapshot_when_no_metrics(mocker):
    datasource = _datasource()
    integration = _integration()
    session = AsyncMock()
    added = []
    session.add = lambda obj: added.append(obj)
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(session))
    mocker.patch.object(
        scheduler_service,
        "get_alive_by_id",
        AsyncMock(side_effect=[datasource, integration]),
    )
    executor = SimpleNamespace(execute_metric_collection=AsyncMock(return_value=[]))
    mocker.patch("backend.services.integration_scheduler.IntegrationExecutor", return_value=executor)
    direct_supplement = mocker.patch.object(
        scheduler_service,
        "_collect_direct_metrics_supplement",
        AsyncMock(return_value={"uptime": 3600}),
    )
    push = mocker.patch.object(scheduler_service, "_push_to_subscribers", AsyncMock())

    await scheduler_service.execute_integration(7)

    assert len(added) == 1
    execution_log = added[0]
    assert execution_log.status == "success"
    assert execution_log.result == {"datasource_count": 1, "metric_count": 0}
    assert execution_log.payload_summary == {"datasource_id": 7}
    assert integration.last_error is None
    assert integration.last_run_at is not None
    session.execute.assert_not_awaited()
    direct_supplement.assert_not_awaited()
    push.assert_not_awaited()
    assert session.commit.await_count == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_all_integration_runs_enabled_sources_and_tolerates_failures(mocker):
    datasource_rows = [
        SimpleNamespace(id=1, inbound_source={"integration_id": 101, "enabled": True}),
        SimpleNamespace(id=2, inbound_source={"integration_id": 102}),
        SimpleNamespace(id=3, inbound_source={"integration_id": 103, "enabled": False}),
        SimpleNamespace(id=4, inbound_source={}),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarsAllResult(datasource_rows))
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(session))
    executed_ids = []

    async def _execute(datasource_id):
        executed_ids.append(datasource_id)
        if datasource_id == 2:
            raise RuntimeError("single datasource failed")

    mocker.patch.object(scheduler_service, "execute_integration", side_effect=_execute)

    await scheduler_service.execute_all_integration()

    assert executed_ids == [1, 2]
