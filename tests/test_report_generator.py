from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.models.report import Report
from backend.services.report_generator import ReportGenerator


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.service
@pytest.mark.asyncio
async def test_generate_inspection_report_records_failed_report_when_datasource_missing(mocker):
    trigger = SimpleNamespace(
        id=5912,
        datasource_id=404,
        trigger_type="scheduled",
        trigger_reason="Scheduled inspection",
        error_message=None,
    )
    added = []

    def add_model(model):
        if isinstance(model, Report):
            model.id = 88
        added.append(model)

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_ScalarResult(trigger), _ScalarResult(None)]),
        add=mocker.Mock(side_effect=add_model),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )

    report_id = await ReportGenerator(db).generate_inspection_report(trigger.id)

    report = added[0]
    assert report_id == 88
    assert report.status == "failed"
    assert report.datasource_id == 404
    assert report.trigger_id == 5912
    assert "not found or has been deleted" in report.error_message
    assert trigger.error_message == report.error_message
    db.commit.assert_awaited_once()
