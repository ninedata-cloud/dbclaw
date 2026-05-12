"""Smoke-test the YAML case library: every case loads, schema is sane."""
import pytest

from backend.evaluation.case_loader import load_all_cases


@pytest.mark.unit
def test_at_least_ten_mysql_cases_load():
    cases = load_all_cases(force_reload=True)
    mysql_cases = [c for c in cases.values() if c.db_type == "mysql"]
    assert len(mysql_cases) >= 10, f"expected ≥10 MySQL cases, got {len(mysql_cases)}"


@pytest.mark.unit
def test_every_case_has_required_fields():
    cases = load_all_cases(force_reload=True)
    assert cases, "no cases discovered"
    for cid, case in cases.items():
        assert case.user_message, f"{cid} missing user_message"
        assert case.expected.required_tools, f"{cid} has empty required_tools"
        assert case.expected.root_causes, f"{cid} has empty root_causes"
        assert case.expected.min_tool_rounds >= 1
        assert case.expected.max_tool_rounds >= case.expected.min_tool_rounds


@pytest.mark.unit
def test_fixture_tools_cover_required_tools():
    """Every required_tools entry should also appear as a fixture (otherwise
    the AI's tool calls return generic fallback responses and the test is moot)."""
    cases = load_all_cases(force_reload=True)
    for cid, case in cases.items():
        fixture_tools = {f.tool for f in case.fixtures}
        for required in case.expected.required_tools:
            assert required in fixture_tools, (
                f"case {cid}: required_tools {required!r} has no matching fixture"
            )


@pytest.mark.unit
def test_case_ids_are_unique():
    cases = load_all_cases(force_reload=True)
    assert len(cases) == len(set(cases.keys()))


@pytest.mark.unit
def test_default_virtual_context_is_added_to_cases():
    case = load_all_cases(force_reload=True)["mysql_slow_query_missing_index"]
    assert case.context.datasource.id == 900001
    assert case.context.datasource.db_type == case.db_type
    assert case.context.host is None


@pytest.mark.unit
def test_os_cases_get_default_virtual_host():
    case = load_all_cases(force_reload=True)["mysql_high_cpu_iowait"]
    assert case.context.datasource.id == 900001
    assert case.context.host is not None
    assert case.context.host.id == 900101
