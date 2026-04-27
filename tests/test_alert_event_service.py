from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.alert_event_service import (
    AlertEventService,
    apply_event_diagnosis_lifecycle,
    hydrate_event_strategy_fields,
    infer_event_strategy,
)
from backend.utils.datetime_helper import now


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._value)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("alert_type", "metric_name", "expected"),
    [
        ("system_error", "connection_status", ("availability", "availability")),
        ("threshold_violation", "disk_usage", ("storage", "storage")),
        ("threshold_violation", "replication_lag", ("replication", "replication")),
        ("threshold_violation", "cpu_usage", ("performance", "performance")),
        ("baseline_deviation", "custom_metric", ("baseline", "performance")),
        ("ai_policy_violation", None, ("ai_policy", "performance")),
        ("custom_expression", "other", ("general", "general")),
    ],
)
def test_infer_event_strategy_maps_known_domains(alert_type, metric_name, expected):
    assert infer_event_strategy(alert_type, metric_name) == expected


@pytest.mark.unit
def test_hydrate_event_strategy_fields_fills_missing_fields_from_status():
    event = SimpleNamespace(
        alert_type="threshold_violation",
        metric_name="disk_usage",
        event_category=None,
        fault_domain=None,
        lifecycle_stage=None,
        status="acknowledged",
    )

    hydrated = hydrate_event_strategy_fields(event)

    assert hydrated.event_category == "storage"
    assert hydrated.fault_domain == "storage"
    assert hydrated.lifecycle_stage == "acknowledged"


@pytest.mark.unit
def test_apply_event_diagnosis_lifecycle_sets_refresh_metadata():
    event = SimpleNamespace(updated_at=None)

    apply_event_diagnosis_lifecycle(
        event,
        stage="escalated",
        trigger_reason="severity_escalated",
    )

    assert event.lifecycle_stage == "escalated"
    assert event.diagnosis_trigger_reason == "severity_escalated"
    assert event.is_diagnosis_refresh_needed is True
    assert event.updated_at is not None


@pytest.mark.service
@pytest.mark.asyncio
async def test_process_new_alert_adds_to_existing_event(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(id=1)
    existing_event = SimpleNamespace(id=10)
    updated_event = SimpleNamespace(id=10, alert_count=2)
    find = mocker.patch.object(AlertEventService, "_find_matching_event", AsyncMock(return_value=existing_event))
    add = mocker.patch.object(AlertEventService, "_add_alert_to_event", AsyncMock(return_value=updated_event))
    create = mocker.patch.object(AlertEventService, "_create_new_event", AsyncMock())

    result = await AlertEventService.process_new_alert(db, alert, time_window_minutes=7)

    assert result is updated_event
    find.assert_awaited_once_with(db, alert, 7)
    add.assert_awaited_once_with(db, existing_event, alert)
    create.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_process_new_alert_creates_event_when_no_match(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(id=1, metric_name=None)
    created_event = SimpleNamespace(id=11)
    mocker.patch.object(AlertEventService, "_find_matching_event", AsyncMock(return_value=None))
    create = mocker.patch.object(AlertEventService, "_create_new_event", AsyncMock(return_value=created_event))

    result = await AlertEventService.process_new_alert(db, alert, time_window_minutes=7)

    assert result is created_event
    create.assert_awaited_once_with(db, alert, "by_alert_type")


@pytest.mark.service
@pytest.mark.asyncio
async def test_create_new_event_sets_initial_metadata():
    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    alert_time = datetime(2026, 1, 1, 9, 0, 0)
    alert = SimpleNamespace(
        id=123,
        datasource_id=5,
        metric_name="cpu_usage",
        alert_type="threshold_violation",
        status="active",
        severity="high",
        title="CPU 高",
        created_at=alert_time,
    )

    event = await AlertEventService._create_new_event(db, alert, "by_metric_name")

    assert added == [event]
    assert event.aggregation_key == "5:cpu_usage"
    assert event.alert_count == 1
    assert event.first_alert_id == 123
    assert event.latest_alert_id == 123
    assert event.event_category == "performance"
    assert event.lifecycle_stage == "created"
    assert event.is_diagnosis_refresh_needed is True
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(event)


@pytest.mark.service
@pytest.mark.asyncio
async def test_add_alert_to_event_escalates_severity_and_requests_diagnosis_refresh():
    db = AsyncMock()
    event = SimpleNamespace(
        id=10,
        latest_alert_id=1,
        alert_count=1,
        event_ended_at=now() - timedelta(minutes=5),
        updated_at=None,
        status="active",
        title="旧告警",
        severity="medium",
        alert_type="threshold_violation",
        is_diagnosis_refresh_needed=False,
    )
    alert = SimpleNamespace(id=2, created_at=now(), status="active", title="新告警", severity="critical", alert_type="threshold_violation")

    updated = await AlertEventService._add_alert_to_event(db, event, alert)

    assert updated is event
    assert event.latest_alert_id == 2
    assert event.alert_count == 2
    assert event.severity == "critical"
    assert event.lifecycle_stage == "escalated"
    assert event.diagnosis_trigger_reason == "severity_escalated"
    assert event.is_diagnosis_refresh_needed is True
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(event)


@pytest.mark.service
@pytest.mark.asyncio
async def test_add_alert_to_event_without_escalation_marks_active():
    db = AsyncMock()
    event = SimpleNamespace(
        latest_alert_id=1,
        alert_count=1,
        event_ended_at=now() - timedelta(minutes=5),
        updated_at=None,
        status="active",
        title="旧告警",
        severity="high",
        alert_type="threshold_violation",
        is_diagnosis_refresh_needed=False,
    )
    alert = SimpleNamespace(id=2, created_at=now(), status="active", title="新告警", severity="medium", alert_type="threshold_violation")

    await AlertEventService._add_alert_to_event(db, event, alert)

    assert event.severity == "high"
    assert event.lifecycle_stage == "active"


@pytest.mark.service
@pytest.mark.asyncio
async def test_update_active_event_time_returns_none_without_aggregation_key():
    event = await AlertEventService.update_active_event_time(AsyncMock(), datasource_id=1)
    assert event is None


@pytest.mark.service
@pytest.mark.asyncio
async def test_check_and_auto_resolve_event_resolves_when_all_alerts_resolved():
    db = AsyncMock()
    event = SimpleNamespace(id=7, status="active", event_ended_at=None, updated_at=None)
    alerts = [SimpleNamespace(status="resolved"), SimpleNamespace(status="resolved")]
    db.execute = AsyncMock(side_effect=[_ScalarResult(event), _ScalarResult(alerts)])

    result = await AlertEventService.check_and_auto_resolve_event(db, 7)

    assert result is event
    assert event.status == "resolved"
    assert event.lifecycle_stage == "recovered"
    assert event.diagnosis_trigger_reason == "event_recovered"
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(event)


@pytest.mark.service
@pytest.mark.asyncio
async def test_check_and_auto_resolve_event_returns_none_when_active_alert_remains():
    db = AsyncMock()
    event = SimpleNamespace(id=7, status="active")
    alerts = [SimpleNamespace(status="resolved"), SimpleNamespace(status="active")]
    db.execute = AsyncMock(side_effect=[_ScalarResult(event), _ScalarResult(alerts)])

    result = await AlertEventService.check_and_auto_resolve_event(db, 7)

    assert result is None
    db.flush.assert_not_awaited()
