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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_scheduler_adds_global_job_and_triggers_now(mocker):
    fake_scheduler = SimpleNamespace(add_job=mocker.Mock())
    mocker.patch.object(scheduler_service, "_ensure_scheduler_started", mocker.Mock())
    mocker.patch.object(scheduler_service, "scheduler", fake_scheduler)
    def _consume_coro(coro):
        coro.close()
        return SimpleNamespace()

    create_task = mocker.patch("asyncio.create_task", side_effect=_consume_coro)

    await scheduler_service.refresh_scheduler(interval_seconds=30, trigger_now=True)

    fake_scheduler.add_job.assert_called_once()
    _, kwargs = fake_scheduler.add_job.call_args
    assert kwargs["id"] == scheduler_service.GLOBAL_INTEGRATION_JOB_ID
    assert kwargs["seconds"] == 30
    create_task.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_scheduler_resolves_interval_from_config_service(mocker):
    fake_scheduler = SimpleNamespace(add_job=mocker.Mock())
    db = AsyncMock()
    mocker.patch.object(scheduler_service, "_ensure_scheduler_started", mocker.Mock())
    mocker.patch.object(scheduler_service, "scheduler", fake_scheduler)
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(db))
    get_interval = mocker.patch(
        "backend.services.monitoring_scheduler_service.get_monitoring_collection_interval_seconds",
        AsyncMock(return_value=45),
    )

    await scheduler_service.refresh_scheduler(interval_seconds=None, trigger_now=False)

    get_interval.assert_awaited_once_with(db)
    _, kwargs = fake_scheduler.add_job.call_args
    assert kwargs["seconds"] == 45


@pytest.mark.service
@pytest.mark.asyncio
async def test_execute_all_integration_filters_enabled_inbound_datasources(mocker):
    ds_enabled = SimpleNamespace(
        id=1,
        inbound_source={"integration_id": 101, "enabled": True},
    )
    ds_disabled = SimpleNamespace(
        id=2,
        inbound_source={"integration_id": 102, "enabled": False},
    )
    ds_no_integration = SimpleNamespace(id=3, inbound_source={})
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [ds_enabled, ds_disabled, ds_no_integration])
        )
    )
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(db))
    exec_integration = mocker.patch.object(scheduler_service, "execute_integration", AsyncMock())

    async def _consume_coroutines(*coroutines, return_exceptions=False):
        assert return_exceptions is True
        for coroutine in coroutines:
            coroutine.close()
        return []

    gather = mocker.patch("asyncio.gather", side_effect=_consume_coroutines)

    await scheduler_service.execute_all_integration()

    # 仅 datasource_id=1 应被调度
    exec_integration.assert_called_once_with(1)
    gather.assert_called_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_execute_integration_skips_non_integration_source(mocker):
    datasource = SimpleNamespace(
        id=1,
        is_active=True,
        metric_source="direct",
        inbound_source={"integration_id": 1, "enabled": True},
    )
    db = AsyncMock()
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(db))
    mocker.patch.object(scheduler_service, "get_alive_by_id", AsyncMock(return_value=datasource))
    executor_cls = mocker.patch("backend.services.integration_scheduler.IntegrationExecutor")

    await scheduler_service.execute_integration(1)

    executor_cls.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_datasource_schedule_refreshes_and_triggers_execute(mocker):
    refresh = mocker.patch.object(scheduler_service, "refresh_scheduler", AsyncMock())

    def _consume_coro(coro):
        coro.close()
        return SimpleNamespace()

    create_task = mocker.patch("asyncio.create_task", side_effect=_consume_coro)

    await scheduler_service.sync_datasource_schedule(88, trigger_now=True)

    refresh.assert_awaited_once_with(trigger_now=False)
    create_task.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unschedule_datasource_only_refreshes_global_job(mocker):
    refresh = mocker.patch.object(scheduler_service, "refresh_scheduler", AsyncMock())

    await scheduler_service.unschedule_datasource(77)

    refresh.assert_awaited_once_with(trigger_now=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_all_integration_delegates_to_refresh_with_trigger(mocker):
    refresh = mocker.patch.object(scheduler_service, "refresh_scheduler", AsyncMock())

    await scheduler_service.schedule_all_integration()

    refresh.assert_awaited_once_with(trigger_now=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_integration_scheduler_delegates_to_refresh_with_trigger(mocker):
    refresh = mocker.patch.object(scheduler_service, "refresh_scheduler", AsyncMock())

    await scheduler_service.start_integration_scheduler()

    refresh.assert_awaited_once_with(trigger_now=True)


@pytest.mark.service
@pytest.mark.asyncio
async def test_execute_integration_returns_when_datasource_missing(mocker):
    db = AsyncMock()
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(db))
    mocker.patch.object(scheduler_service, "get_alive_by_id", AsyncMock(return_value=None))
    executor_cls = mocker.patch("backend.services.integration_scheduler.IntegrationExecutor")

    await scheduler_service.execute_integration(123)

    executor_cls.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_execute_integration_returns_when_inbound_integration_id_missing(mocker):
    datasource = SimpleNamespace(
        id=1,
        is_active=True,
        metric_source="integration",
        inbound_source={"enabled": True},
    )
    db = AsyncMock()
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(db))
    mocker.patch.object(scheduler_service, "get_alive_by_id", AsyncMock(return_value=datasource))
    executor_cls = mocker.patch("backend.services.integration_scheduler.IntegrationExecutor")

    await scheduler_service.execute_integration(1)

    executor_cls.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_execute_integration_returns_when_integration_not_enabled(mocker):
    datasource = SimpleNamespace(
        id=1,
        is_active=True,
        metric_source="integration",
        inbound_source={"integration_id": 100, "enabled": True},
    )
    integration = SimpleNamespace(id=100, is_enabled=False, integration_type="inbound_metric")
    db = AsyncMock()
    db.commit = AsyncMock()
    mocker.patch.object(scheduler_service, "async_session", lambda: _AsyncSessionContext(db))
    get_alive = mocker.patch.object(
        scheduler_service,
        "get_alive_by_id",
        AsyncMock(side_effect=[datasource, integration]),
    )
    executor_cls = mocker.patch("backend.services.integration_scheduler.IntegrationExecutor")

    await scheduler_service.execute_integration(1)

    assert get_alive.await_count == 2
    executor_cls.assert_not_called()
