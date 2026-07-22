from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import metric_collector


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.service
@pytest.mark.asyncio
async def test_route_alert_engine_returns_when_no_enabled_config(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(1))
    datasource = SimpleNamespace(id=1)
    mocker.patch.object(metric_collector, "_get_enabled_inspection_config", AsyncMock(return_value=None))
    threshold = mocker.patch.object(metric_collector, "_check_thresholds_and_trigger", AsyncMock())

    await metric_collector._route_alert_engine(db, datasource, {"cpu": 90})

    threshold.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_route_alert_engine_uses_ai_mode(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(2))
    datasource = SimpleNamespace(id=2)
    config = SimpleNamespace(ai_shadow_enabled=False)
    mocker.patch.object(metric_collector, "_get_enabled_inspection_config", AsyncMock(return_value=config))
    mocker.patch("backend.services.metric_collector.resolve_effective_inspection_config", AsyncMock(return_value=config))
    mocker.patch(
        "backend.services.alert_ai_service.resolve_effective_alert_engine_mode",
        AsyncMock(return_value="ai"),
    )
    ai_check = mocker.patch.object(metric_collector, "_check_ai_alerts_and_trigger", AsyncMock())
    threshold = mocker.patch.object(metric_collector, "_check_thresholds_and_trigger", AsyncMock())

    await metric_collector._route_alert_engine(db, datasource, {"cpu": 90})

    ai_check.assert_awaited_once()
    threshold.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_route_alert_engine_threshold_with_ai_shadow(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(3))
    datasource = SimpleNamespace(id=3)
    config = SimpleNamespace(ai_shadow_enabled=True)
    mocker.patch.object(metric_collector, "_get_enabled_inspection_config", AsyncMock(return_value=config))
    mocker.patch("backend.services.metric_collector.resolve_effective_inspection_config", AsyncMock(return_value=config))
    mocker.patch(
        "backend.services.alert_ai_service.resolve_effective_alert_engine_mode",
        AsyncMock(return_value="threshold"),
    )
    ai_check = mocker.patch.object(metric_collector, "_check_ai_alerts_and_trigger", AsyncMock())
    threshold = mocker.patch.object(metric_collector, "_check_thresholds_and_trigger", AsyncMock())

    await metric_collector._route_alert_engine(db, datasource, {"cpu": 90})

    threshold.assert_awaited_once_with(db, datasource.id, {"cpu": 90})
    ai_check.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_route_alert_engine_swallows_config_errors(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(4))
    datasource = SimpleNamespace(id=4)
    mocker.patch.object(
        metric_collector,
        "_get_enabled_inspection_config",
        AsyncMock(side_effect=RuntimeError("config unavailable")),
    )
    threshold = mocker.patch.object(metric_collector, "_check_thresholds_and_trigger", AsyncMock())
    ai_check = mocker.patch.object(metric_collector, "_check_ai_alerts_and_trigger", AsyncMock())

    await metric_collector._route_alert_engine(db, datasource, {"cpu": 90})

    threshold.assert_not_awaited()
    ai_check.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_route_alert_engine_skips_deleted_datasource(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    datasource = SimpleNamespace(id=9)
    config_lookup = mocker.patch.object(metric_collector, "_get_enabled_inspection_config", AsyncMock())
    threshold = mocker.patch.object(metric_collector, "_check_thresholds_and_trigger", AsyncMock())
    ai_check = mocker.patch.object(metric_collector, "_check_ai_alerts_and_trigger", AsyncMock())

    await metric_collector._route_alert_engine(db, datasource, {"cpu": 90})

    config_lookup.assert_not_awaited()
    threshold.assert_not_awaited()
    ai_check.assert_not_awaited()
