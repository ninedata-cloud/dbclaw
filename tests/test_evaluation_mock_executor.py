import json

import pytest

from backend.agent.tool_override import (
    get_tool_override,
    reset_tool_override,
    set_tool_override,
)
from backend.evaluation.case_loader import CaseExpected, EvalCase, EvalHostContext, FixtureRule
from backend.evaluation.mock_executor import CallRecorder, make_mock_override, validate_tool_arguments


def _case_with(rules):
    return EvalCase(
        id="t",
        category="test",
        db_type="mysql",
        title="t",
        user_message="hi",
        fixtures=rules,
        expected=CaseExpected(),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_override_returns_matching_fixture():
    case = _case_with([
        FixtureRule(tool="mysql_get_db_status", args="any", response={"qps": 100}),
    ])
    rec = CallRecorder()
    override = make_mock_override(case, rec)

    result, exec_ms, viz = await override("mysql_get_db_status", {"datasource_id": 900001}, "skill")
    assert json.loads(result) == {"qps": 100}
    assert viz is None
    assert exec_ms >= 0
    assert len(rec.calls) == 1
    assert rec.calls[0].matched is True
    assert rec.calls[0].argument_valid is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_override_returns_fallback_when_no_match():
    case = _case_with([
        FixtureRule(tool="other_tool", args="any", response={}),
    ])
    rec = CallRecorder()
    override = make_mock_override(case, rec)

    result, _, _ = await override("missing_tool", {}, "skill")
    payload = json.loads(result)
    assert payload["success"] is True
    assert "no fixture matched" in payload["note"]
    assert rec.calls[0].matched is False
    assert rec.unmatched_count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_override_rejects_missing_datasource_id_for_db_skill():
    case = _case_with([
        FixtureRule(tool="mysql_get_db_status", args="any", response={"qps": 100}),
    ])
    rec = CallRecorder()
    override = make_mock_override(case, rec)

    result, _, _ = await override("mysql_get_db_status", {}, "skill")

    payload = json.loads(result)
    assert payload["success"] is False
    assert payload["error"] == "invalid_evaluation_tool_arguments"
    assert rec.calls[0].matched is False
    assert rec.calls[0].argument_valid is False
    assert rec.invalid_argument_count() == 1


@pytest.mark.unit
def test_validate_tool_arguments_accepts_correct_host_for_os_skill():
    case = _case_with([
        FixtureRule(tool="get_os_metrics", args="any", response={}),
    ])
    case.context.host = EvalHostContext(id=900101)

    valid, errors = validate_tool_arguments(case, "get_os_metrics", {"host_id": 900101})

    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_validate_tool_arguments_rejects_wrong_host_for_os_skill():
    case = _case_with([
        FixtureRule(tool="get_os_metrics", args="any", response={}),
    ])
    case.context.host = EvalHostContext(id=900101)

    valid, errors = validate_tool_arguments(case, "get_os_metrics", {"host_id": 7})

    assert valid is False
    assert "host_id 7 != expected 900101" in errors


@pytest.mark.unit
def test_contextvar_set_and_reset():
    assert get_tool_override() is None

    async def dummy(name, args, kind):
        return "x", 0, None

    token = set_tool_override(dummy)
    assert get_tool_override() is dummy
    reset_tool_override(token)
    assert get_tool_override() is None
