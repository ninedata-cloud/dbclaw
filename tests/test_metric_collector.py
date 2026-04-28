import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import metric_collector


class _AsyncSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ScalarsAllResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.unit
def test_subscribe_and_unsubscribe_updates_registry():
    metric_collector._metric_subscribers.clear()

    queue = metric_collector.subscribe(10)
    assert 10 in metric_collector._metric_subscribers
    assert queue in metric_collector._metric_subscribers[10]

    metric_collector.unsubscribe(10, queue)
    assert 10 not in metric_collector._metric_subscribers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_push_to_subscribers_removes_full_queue():
    metric_collector._metric_subscribers.clear()
    full_queue = asyncio.Queue(maxsize=1)
    await full_queue.put({"old": True})
    good_queue = asyncio.Queue(maxsize=1)
    metric_collector._metric_subscribers[1] = [full_queue, good_queue]

    await metric_collector._push_to_subscribers(1, {"new": True})

    assert full_queue not in metric_collector._metric_subscribers[1]
    assert await good_queue.get() == {"new": True}


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_all_metrics_handles_network_probe_failure(mocker):
    mocker.patch("backend.services.network_probe.check_network", AsyncMock(return_value=False))
    mocker.patch("backend.services.metric_collector._handle_network_probe_failure", AsyncMock())
    auto_resolve = mocker.patch("backend.services.metric_collector._auto_resolve_network_probe_alerts", AsyncMock())
    collect_one = mocker.patch("backend.services.metric_collector.collect_metrics_for_connection", AsyncMock())

    probe_db = AsyncMock()
    mocker.patch.object(metric_collector, "async_session", lambda: _AsyncSessionContext(probe_db))
    mocker.patch("backend.services.config_service.get_config", AsyncMock(return_value="127.0.0.1"))

    await metric_collector.collect_all_metrics()

    auto_resolve.assert_not_awaited()
    collect_one.assert_not_called()


@pytest.mark.unit
def test_start_scheduler_starts_when_not_running(mocker):
    fake_scheduler = SimpleNamespace(
        running=False,
        add_job=mocker.Mock(),
        start=mocker.Mock(),
    )
    metric_collector.scheduler = fake_scheduler

    metric_collector.start_scheduler(interval_seconds=15)

    fake_scheduler.add_job.assert_called_once()
    fake_scheduler.start.assert_called_once()


@pytest.mark.unit
def test_stop_scheduler_shutdown_running_scheduler(mocker):
    fake_scheduler = SimpleNamespace(running=True, shutdown=mocker.Mock())
    metric_collector.scheduler = fake_scheduler

    metric_collector.stop_scheduler()

    fake_scheduler.shutdown.assert_called_once_with(wait=False)


@pytest.mark.unit
def test_stop_scheduler_when_none_is_noop():
    metric_collector.scheduler = None
    metric_collector.stop_scheduler()


@pytest.mark.unit
def test_stop_scheduler_when_not_running_does_not_shutdown(mocker):
    fake_scheduler = SimpleNamespace(running=False, shutdown=mocker.Mock())
    metric_collector.scheduler = fake_scheduler
    metric_collector.stop_scheduler()
    fake_scheduler.shutdown.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_push_to_subscribers_no_subscribers_is_noop():
    metric_collector._metric_subscribers.clear()
    await metric_collector._push_to_subscribers(999, {"x": 1})


@pytest.mark.unit
def test_start_scheduler_when_already_running_skips_start(mocker):
    fake_scheduler = SimpleNamespace(
        running=True,
        add_job=mocker.Mock(),
        start=mocker.Mock(),
    )
    metric_collector.scheduler = fake_scheduler
    metric_collector.start_scheduler(interval_seconds=30)
    fake_scheduler.add_job.assert_called_once()
    fake_scheduler.start.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_all_metrics_skips_gather_when_no_datasources(mocker):
    mocker.patch("backend.services.network_probe.check_network", AsyncMock(return_value=True))
    mocker.patch("backend.services.metric_collector._auto_resolve_network_probe_alerts", AsyncMock())
    gather = mocker.patch("backend.services.metric_collector.asyncio.gather", AsyncMock())
    list_db = AsyncMock()
    list_db.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: []))
    mocker.patch.object(metric_collector, "async_session", lambda: _AsyncSessionContext(list_db))
    mocker.patch("backend.services.config_service.get_config", AsyncMock(return_value="127.0.0.1"))

    await metric_collector.collect_all_metrics()

    gather.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_all_metrics_dispatches_each_active_datasource(mocker):
    mocker.patch("backend.services.network_probe.check_network", AsyncMock(return_value=True))
    mocker.patch("backend.services.metric_collector._auto_resolve_network_probe_alerts", AsyncMock())
    list_db = AsyncMock()
    list_db.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: [(1,), (2,)]))
    mocker.patch.object(metric_collector, "async_session", lambda: _AsyncSessionContext(list_db))
    mocker.patch("backend.services.config_service.get_config", AsyncMock(return_value="127.0.0.1"))
    collect_one = mocker.patch("backend.services.metric_collector.collect_metrics_for_connection", AsyncMock())

    async def _consume_coroutines(*coroutines, return_exceptions=False):
        assert return_exceptions is True
        assert len(coroutines) == 2
        for coroutine in coroutines:
            coroutine.close()
        return []

    gather = mocker.patch("backend.services.metric_collector.asyncio.gather", side_effect=_consume_coroutines)

    await metric_collector.collect_all_metrics()

    assert collect_one.call_count == 2
    collect_one.assert_any_call(1)
    collect_one.assert_any_call(2)
    gather.assert_called_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_metrics_for_connection_returns_early_when_datasource_missing(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    mocker.patch.object(metric_collector, "async_session", lambda: _AsyncSessionContext(db))
    get_connector = mocker.patch("backend.services.metric_collector.get_connector")

    await metric_collector.collect_metrics_for_connection(99)

    get_connector.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_metrics_for_connection_skips_integration_metric_source(mocker):
    ds = SimpleNamespace(
        id=7,
        metric_source="integration",
        db_type="mysql",
        host="h",
        port=3306,
        username="u",
        password_encrypted=None,
        database="d",
        extra_params={},
        silence_until=None,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: ds))
    mocker.patch.object(metric_collector, "async_session", lambda: _AsyncSessionContext(db))
    get_connector = mocker.patch("backend.services.metric_collector.get_connector")

    await metric_collector.collect_metrics_for_connection(7)

    get_connector.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_auto_resolve_recovered_alerts_uses_original_threshold_when_rule_is_raised(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(
        id=1,
        metric_name="cpu_usage",
        threshold_value=75,
    )
    db.execute = AsyncMock(return_value=_ScalarsAllResult([alert]))
    resolve_alert = mocker.patch(
        "backend.services.alert_service.AlertService.resolve_alert",
        AsyncMock(),
    )

    await metric_collector._auto_resolve_recovered_alerts(
        db=db,
        datasource_id=10,
        metrics={"cpu_usage": 76.6},
        threshold_rules={"cpu_usage": {"threshold": 80, "duration": 60}},
        current_violations=[],
    )

    resolve_alert.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_auto_resolve_recovered_alerts_resolves_below_original_threshold(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(
        id=1,
        metric_name="cpu_usage",
        threshold_value=75,
    )
    db.execute = AsyncMock(return_value=_ScalarsAllResult([alert]))
    resolve_alert = mocker.patch(
        "backend.services.alert_service.AlertService.resolve_alert",
        AsyncMock(),
    )

    await metric_collector._auto_resolve_recovered_alerts(
        db=db,
        datasource_id=10,
        metrics={"cpu_usage": 74.9},
        threshold_rules={"cpu_usage": {"threshold": 80, "duration": 60}},
        current_violations=[],
    )

    resolve_alert.assert_awaited_once_with(db, 1, resolved_value=74.9)
