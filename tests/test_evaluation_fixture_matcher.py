import json

import pytest

from backend.evaluation.case_loader import FixtureRule
from backend.evaluation.fixture_matcher import (
    fallback_response,
    find_fixture,
    render_response,
)


@pytest.mark.unit
def test_match_any_args_always_hits():
    rule = FixtureRule(tool="t", args="any", response={"ok": True})
    assert find_fixture([rule], "t", {"connection_id": 1}) is rule


@pytest.mark.unit
def test_match_exact_dict():
    rule = FixtureRule(tool="t", args={"x": 1}, response={"ok": True})
    assert find_fixture([rule], "t", {"x": 1, "extra": "z"}) is rule
    assert find_fixture([rule], "t", {"x": 2}) is None


@pytest.mark.unit
def test_match_sql_pattern_regex():
    rule = FixtureRule(
        tool="mysql_explain_query",
        args={"sql_pattern": r"orders.*status.*pending"},
        response={"plan": []},
    )
    args = {"sql": "EXPLAIN SELECT * FROM orders WHERE status='pending'"}
    assert find_fixture([rule], "mysql_explain_query", args) is rule

    bad = {"sql": "SELECT * FROM users"}
    assert find_fixture([rule], "mysql_explain_query", bad) is None


@pytest.mark.unit
def test_match_returns_first_winner():
    a = FixtureRule(tool="t", args={"x": 1}, response="first")
    b = FixtureRule(tool="t", args="any", response="second")
    assert find_fixture([a, b], "t", {"x": 1}).response == "first"
    assert find_fixture([a, b], "t", {"x": 9}).response == "second"


@pytest.mark.unit
def test_render_response_serializes_dict():
    rule = FixtureRule(tool="t", args="any", response={"a": 1, "b": [1, 2]})
    text = render_response(rule)
    assert json.loads(text) == {"a": 1, "b": [1, 2]}


@pytest.mark.unit
def test_render_response_passes_through_string():
    rule = FixtureRule(tool="t", args="any", response='{"raw": true}')
    assert render_response(rule) == '{"raw": true}'


@pytest.mark.unit
def test_fallback_response_marks_unmatched_but_not_error():
    text = fallback_response("unknown_tool", {"x": 1})
    payload = json.loads(text)
    assert payload["success"] is True
    assert "no fixture matched" in payload["note"]
