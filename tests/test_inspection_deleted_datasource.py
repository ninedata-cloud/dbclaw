from unittest.mock import AsyncMock

import pytest

from backend.services.inspection_service import InspectionService


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.service
@pytest.mark.asyncio
async def test_trigger_inspection_skips_deleted_datasource(mocker):
    service = InspectionService(db_session_factory=mocker.Mock())
    db = AsyncMock()
    db.add = mocker.Mock()
    mocker.patch(
        "backend.services.inspection_service.get_alive_by_id",
        AsyncMock(return_value=None),
    )
    background_task = mocker.patch.object(service, "_create_tracked_task")

    trigger_id = await service.trigger_inspection(
        db,
        datasource_id=9,
        trigger_type="scheduled",
    )

    assert trigger_id is None
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    background_task.assert_not_called()


@pytest.mark.service
@pytest.mark.asyncio
async def test_generate_report_skips_trigger_for_deleted_datasource(mocker):
    service = InspectionService(db_session_factory=mocker.Mock())
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    generator = mocker.patch("backend.services.report_generator.ReportGenerator")

    await service._generate_report(db, trigger_id=17)

    generator.assert_not_called()
    db.commit.assert_not_awaited()
