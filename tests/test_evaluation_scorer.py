import pytest

from backend.evaluation.case_loader import CaseExpected, EvalCase
from backend.evaluation.fixture_matcher import FixtureRule  # type: ignore
from backend.evaluation.mock_executor import CallRecorder, RecordedToolCall
from backend.evaluation.scorer import (
    WEIGHT_ACTION,
    WEIGHT_EFFICIENCY,
    WEIGHT_LATENCY,
    WEIGHT_ROOT_CAUSE,
    WEIGHT_STRUCTURE,
    WEIGHT_TOOL_SELECTION,
    combine_scores,
    compute_programmatic,
    score_action_keywords,
    score_efficiency,
    score_structure,
    score_tool_selection,
)


def _make_case(**overrides) -> EvalCase:
    expected = CaseExpected(**overrides.pop("expected", {}))
    return EvalCase(
        id=overrides.pop("id", "c"),
        category=overrides.pop("category", "test"),
        db_type="mysql",
        title="t",
        user_message="u",
        fixtures=[],
        expected=expected,
        description=None,
        difficulty="easy",
    )


def _recorder(tools):
    rec = CallRecorder()
    for t in tools:
        rec.calls.append(
            RecordedToolCall(
                tool_name=t, args={}, kind="skill", matched=True,
                argument_valid=True, argument_errors=[],
                result_preview="", timestamp_ms=0,
            )
        )
    return rec


@pytest.mark.unit
def test_tool_selection_full_recall_no_forbidden():
    case = _make_case(expected={"required_tools": ["a", "b"], "forbidden_tools": ["bad"]})
    rec = _recorder(["a", "b"])
    dim, missing, forbidden_hits = score_tool_selection(case, rec)
    assert missing == []
    assert forbidden_hits == []
    assert dim.score == WEIGHT_TOOL_SELECTION


@pytest.mark.unit
def test_tool_selection_partial_recall():
    case = _make_case(expected={"required_tools": ["a", "b", "c"]})
    rec = _recorder(["a"])
    dim, missing, _ = score_tool_selection(case, rec)
    assert missing == ["b", "c"]
    assert dim.score == pytest.approx(WEIGHT_TOOL_SELECTION * (1 / 3))


@pytest.mark.unit
def test_tool_selection_forbidden_hits_apply_penalty():
    case = _make_case(expected={"required_tools": ["a"], "forbidden_tools": ["bad"]})
    rec = _recorder(["a", "bad"])
    dim, _, forbidden_hits = score_tool_selection(case, rec)
    assert forbidden_hits == ["bad"]
    # full recall (1.0) minus 0.5 penalty = 0.5 * weight
    assert dim.score == pytest.approx(WEIGHT_TOOL_SELECTION * 0.5)


@pytest.mark.unit
def test_tool_selection_requires_valid_matched_required_calls():
    case = _make_case(expected={"required_tools": ["a", "b"]})
    rec = CallRecorder()
    rec.calls.extend([
        RecordedToolCall(
            tool_name="a", args={}, kind="skill", matched=True,
            argument_valid=True, argument_errors=[],
            result_preview="", timestamp_ms=0,
        ),
        RecordedToolCall(
            tool_name="b", args={}, kind="skill", matched=False,
            argument_valid=False, argument_errors=["missing datasource_id"],
            result_preview="", timestamp_ms=0,
        ),
    ])

    dim, missing, _ = score_tool_selection(case, rec)

    assert missing == ["b"]
    assert dim.score == pytest.approx(WEIGHT_TOOL_SELECTION * 0.5)


@pytest.mark.unit
def test_structure_must_contain_and_must_not_contain():
    case = _make_case(expected={
        "conclusion_must_contain": ["诊断结论", "建议动作"],
        "conclusion_must_not_contain": ["也许"],
    })
    good = "### 诊断结论\n...\n### 建议动作\n..."
    bad = "### 诊断结论\n也许是这个原因"
    assert score_structure(case, good).score == WEIGHT_STRUCTURE
    assert score_structure(case, bad).score < WEIGHT_STRUCTURE


@pytest.mark.unit
def test_efficiency_within_window_full_marks():
    case = _make_case(expected={"min_tool_rounds": 2, "max_tool_rounds": 5})
    rec = _recorder(["a", "b", "c"])
    dim = score_efficiency(case, rec)
    assert dim.score == WEIGHT_EFFICIENCY


@pytest.mark.unit
def test_efficiency_too_few_calls_partial():
    case = _make_case(expected={"min_tool_rounds": 4, "max_tool_rounds": 8})
    rec = _recorder(["a"])
    dim = score_efficiency(case, rec)
    assert 0 < dim.score < WEIGHT_EFFICIENCY


@pytest.mark.unit
def test_efficiency_overage_degrades_but_floors_above_zero():
    case = _make_case(expected={"min_tool_rounds": 1, "max_tool_rounds": 4})
    rec = _recorder(["a"] * 12)
    dim = score_efficiency(case, rec)
    assert dim.score >= WEIGHT_EFFICIENCY * 0.2 - 0.001


@pytest.mark.unit
def test_action_keywords_all_or_nothing_per_entry():
    case = _make_case(expected={"required_actions": [
        {"keywords": ["CREATE INDEX", "status"]},
    ]})
    hits, total, _ = score_action_keywords(case, "请 CREATE INDEX status_idx ON orders(status)")
    assert hits == 1 and total == 1

    hits, total, _ = score_action_keywords(case, "请创建索引")
    assert hits == 0 and total == 1


@pytest.mark.unit
def test_combine_scores_caps_at_100():
    case = _make_case(expected={
        "required_tools": ["a"],
        "conclusion_must_contain": ["x"],
    })
    rec = _recorder(["a"])
    prog = compute_programmatic(case, rec, "x" * 200, latency_ms=1000)
    total, dims = combine_scores(prog, WEIGHT_ROOT_CAUSE, WEIGHT_ACTION)
    assert 0 <= total <= 100
    # latency 1s is full marks
    latency = next(d for d in dims if d["name"] == "latency")
    assert latency["score"] == WEIGHT_LATENCY
