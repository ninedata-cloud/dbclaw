from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.alert_service import (
    _find_in_progress_diagnosis,
    _find_recent_diagnosis,
    run_sync_diagnosis,
)


@pytest.mark.asyncio
async def test_find_recent_diagnosis_uses_alert_type_and_completion_window():
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
    assert "diagnosis_completed_at" in query_text
    assert "alert_events.metric_name =" not in query_text
    assert "alert_events.last_updated >=" not in query_text


@pytest.mark.asyncio
async def test_find_in_progress_diagnosis_uses_alert_type_and_started_at():
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    current_event = SimpleNamespace(
        id=11,
        datasource_id=9,
        alert_type="system_error",
    )

    with patch("backend.services.alert_service._get_diagnosis_dedup_window_minutes", return_value=30):
        await _find_in_progress_diagnosis(db, current_event)

    query_text = str(db.execute.call_args.args[0])
    assert "alert_events.alert_type =" in query_text
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
