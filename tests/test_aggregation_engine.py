from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.aggregation_engine import AggregationEngine
from backend.utils.datetime_helper import now


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_rule_allows_alert_without_event_id(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(event_id=None)
    subscription = SimpleNamespace(id=10)
    # Isolate this case from config-service DB access.
    mocker.patch.object(AggregationEngine, "_get_notification_cooldown_minutes", AsyncMock(return_value=60))

    should_send = await AggregationEngine._default_aggregation_rule(db, alert, subscription)

    assert should_send is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_rule_suppresses_within_cooldown_without_escalation(mocker):
    sent_at = now() - timedelta(minutes=5)
    delivery_log = SimpleNamespace(sent_at=sent_at, created_at=sent_at)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result([(delivery_log, "medium")]))
    alert = SimpleNamespace(id=1, event_id=100, severity="medium")
    subscription = SimpleNamespace(id=10)
    mocker.patch.object(AggregationEngine, "_get_notification_cooldown_minutes", AsyncMock(return_value=60))

    should_send = await AggregationEngine._default_aggregation_rule(db, alert, subscription)

    assert should_send is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_rule_allows_when_severity_escalates(mocker):
    sent_at = now() - timedelta(minutes=5)
    delivery_log = SimpleNamespace(sent_at=sent_at, created_at=sent_at)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result([(delivery_log, "medium")]))
    alert = SimpleNamespace(id=1, event_id=101, severity="high")
    subscription = SimpleNamespace(id=11)
    mocker.patch.object(AggregationEngine, "_get_notification_cooldown_minutes", AsyncMock(return_value=60))

    should_send = await AggregationEngine._default_aggregation_rule(db, alert, subscription)

    assert should_send is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_custom_script_falls_back_to_default_rule_on_error(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])))
    alert = SimpleNamespace(
        datasource_id=1,
        alert_type="threshold_violation",
        severity="high",
        metric_name="cpu_usage",
        metric_value=95,
        threshold_value=80,
        title="CPU告警",
        content="CPU过高",
    )
    subscription = SimpleNamespace(id=20, aggregation_script="def should_send(*args): return True")
    mocker.patch.object(AggregationEngine, "_execute_sandboxed", side_effect=RuntimeError("boom"))
    fallback = mocker.patch.object(AggregationEngine, "_default_aggregation_rule", AsyncMock(return_value=True))

    should_send = await AggregationEngine.execute_custom_script(db, alert, subscription)

    assert should_send is True
    fallback.assert_awaited_once()
