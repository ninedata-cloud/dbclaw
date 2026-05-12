from unittest.mock import AsyncMock

import pytest

from backend.evaluation.case_loader import CaseExpected, EvalCase, FixtureRule
from backend.evaluation.runner import run_case


class _DB:
    def __init__(self):
        self.added = []
        self.add = self.added.append
        self.commit = AsyncMock()
        self.refresh = AsyncMock(side_effect=self._refresh)

    async def _refresh(self, obj):
        obj.id = 123


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_case_passes_virtual_context_without_session_asset_ids(mocker):
    captured = {}

    async def _fake_conversation(**kwargs):
        captured.update(kwargs)
        yield {"type": "error", "message": "stop before model call"}

    mocker.patch("backend.evaluation.runner.run_conversation_with_skills", _fake_conversation)
    case = EvalCase(
        id="ctx",
        category="test",
        db_type="mysql",
        title="ctx",
        user_message="hi",
        fixtures=[FixtureRule(tool="mysql_get_db_status", args="any", response={})],
        expected=CaseExpected(required_tools=["mysql_get_db_status"]),
    )
    db = _DB()

    output = await run_case(case, db, ai_model_id=7, user_id=2, judge_model_id=None)

    session = db.added[0]
    assert session.datasource_id is None
    assert session.host_id is None
    assert captured["datasource_id"] is None
    assert captured["context_override"]["datasource"]["id"] == 900001
    assert output.session_id == 123
