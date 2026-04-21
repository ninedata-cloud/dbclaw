import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.datasource import Datasource
from backend.routers import datasource as datasource_router
from backend.schemas.datasource import DatasourceSilenceRequest


def test_datasource_silence_request_accepts_half_hour_and_240_hours():
    half_hour = DatasourceSilenceRequest(hours=0.5, reason="变更窗口")
    max_hours = DatasourceSilenceRequest(hours=240)

    assert half_hour.hours == 0.5
    assert max_hours.hours == 240


def test_datasource_silence_request_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        DatasourceSilenceRequest(hours=0.49)

    with pytest.raises(ValidationError):
        DatasourceSilenceRequest(hours=240.1)


@pytest.mark.asyncio
async def test_set_datasource_silence_supports_fractional_hours(monkeypatch):
    fixed_now = datetime(2026, 4, 6, 10, 0, 0)
    datasource = Datasource(id=11, name="订单库")
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    monkeypatch.setattr("backend.utils.datetime_helper.now", lambda: fixed_now)
    monkeypatch.setattr(datasource_router, "get_alive_by_id", AsyncMock(return_value=datasource))

    response = await datasource_router.set_datasource_silence(
        datasource_id=11,
        request=DatasourceSilenceRequest(hours=0.5, reason="发布观察期"),
        db=db,
    )

    assert datasource.silence_reason == "发布观察期"
    assert datasource.silence_until == fixed_now + timedelta(minutes=30)
    assert response.is_silenced is True
    assert response.remaining_hours == 0.5
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(datasource)
