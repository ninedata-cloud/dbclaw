import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers.metrics import get_metrics
from backend.utils.datetime_helper import normalize_local_datetime


def _mock_scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_all_result(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def test_normalize_local_datetime_converts_timezone_aware_value():
    aware = datetime(2026, 4, 1, 8, 4, 0, tzinfo=timezone.utc)

    normalized = normalize_local_datetime(aware)

    assert normalized == aware.astimezone().replace(tzinfo=None)
    assert normalized.tzinfo is None


@pytest.mark.asyncio
async def test_get_metrics_normalizes_time_range_before_query():
    db = MagicMock()
    captured_statements = []

    async def _execute(statement):
        captured_statements.append(statement)
        if len(captured_statements) == 1:
            return _mock_scalar_result(None)
        return _mock_scalars_all_result([])

    db.execute = AsyncMock(side_effect=_execute)

    start_time = datetime(2026, 4, 1, 8, 4, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 4, 6, 19, 4, 0, tzinfo=timezone.utc)

    await get_metrics(
        conn_id=375,
        metric_type="cpu_usage",
        start_time=start_time,
        end_time=end_time,
        limit=10000,
        db=db,
    )

    query_params = captured_statements[1].compile().params
    datetime_params = [value for value in query_params.values() if isinstance(value, datetime)]

    assert len(datetime_params) == 2
    assert all(value.tzinfo is None for value in datetime_params)
    assert normalize_local_datetime(start_time) in datetime_params
    assert normalize_local_datetime(end_time) in datetime_params
