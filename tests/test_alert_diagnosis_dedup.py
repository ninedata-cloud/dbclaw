from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.alert_service import (
    _find_in_progress_diagnosis,
    _find_recent_diagnosis,
    normalize_event_ai_config,
    run_sync_diagnosis,
    should_refresh_event_diagnosis,
)
from backend.utils.datetime_helper import now


@pytest.mark.asyncio
async def test_find_recent_diagnosis_uses_metric_name_and_completion_window():
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    current_event = SimpleNamespace(
        id=10,
        datasource_id=7,
        alert_type="threshold_violation",
        metric_name="cpu_usage",
    )

    with patch("backend.services.alert_service._get_diagnosis_dedup_window_minutes", return_value=60):
        await _find_recent_diagnosis(db, current_event)

    query_text = str(db.execute.call_args.args[0])
    assert "alert_events.alert_type =" in query_text
    assert "alert_events.metric_name =" in query_text
    assert "diagnosis_completed_at" in query_text
    assert "alert_events.last_updated >=" not in query_text


@pytest.mark.asyncio
async def test_find_in_progress_diagnosis_uses_metric_name_and_started_at():
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    current_event = SimpleNamespace(
        id=11,
        datasource_id=9,
        alert_type="system_error",
        metric_name="connection_status",
    )

    with patch("backend.services.alert_service._get_diagnosis_dedup_window_minutes", return_value=30):
        await _find_in_progress_diagnosis(db, current_event)

    query_text = str(db.execute.call_args.args[0])
    assert "alert_events.alert_type =" in query_text
    assert "alert_events.metric_name =" in query_text
    assert "diagnosis_started_at" in query_text
    assert "diagnosis_status IN" in query_text
    assert "alert_events.diagnosis_started_at >=" in query_text


@pytest.mark.asyncio
async def test_run_sync_diagnosis_skips_when_same_type_diagnosis_in_progress():
    db = AsyncMock(spec=AsyncSession)
    current_event = SimpleNamespace(
        id=12,
        datasource_id=3,
        alert_type="threshold_violation",
        metric_name="memory_usage",
        diagnosis_status=None,
        ai_diagnosis_summary=None,
        diagnosis_source_event_id=None,
    )
    in_progress_event = SimpleNamespace(id=99)

    result = MagicMock()
    result.scalar_one_or_none.return_value = current_event
    db.execute.return_value = result

    with patch("backend.services.alert_service._find_recent_diagnosis", new=AsyncMock(return_value=None)):
        with patch("backend.services.alert_service._find_in_progress_diagnosis", new=AsyncMock(return_value=in_progress_event)):
            response = await run_sync_diagnosis(db, alert_event_id=12, timeout_seconds=5)

    assert response["status"] == "pending"
    assert current_event.diagnosis_status == "pending"
    assert current_event.diagnosis_source_event_id == 99
    db.commit.assert_awaited()


def test_should_refresh_event_diagnosis_on_escalation_and_staleness():
    event = SimpleNamespace(
        ai_diagnosis_summary="CPU 持续高负载",
        diagnosis_trigger_reason="severity_escalated",
        diagnosis_refresh_needed=True,
        diagnosis_completed_at=now() - timedelta(minutes=5),
        status="active",
    )

    assert should_refresh_event_diagnosis(event, normalize_event_ai_config({})) is True

    event.diagnosis_trigger_reason = None
    event.diagnosis_refresh_needed = False
    event.diagnosis_completed_at = now() - timedelta(minutes=40)
    assert should_refresh_event_diagnosis(event, normalize_event_ai_config({"stale_recheck_minutes": 30})) is True
