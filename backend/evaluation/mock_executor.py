"""Mock tool executor used during evaluation runs.

Records every tool call the AI makes and returns the matching fixture
response (or a non-error fallback when no fixture matches).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.evaluation.case_loader import EvalCase, OS_CONTEXT_TOOLS
from backend.evaluation.fixture_matcher import (
    fallback_response,
    find_fixture,
    render_response,
)


@dataclass
class RecordedToolCall:
    tool_name: str
    args: Dict[str, Any]
    kind: str           # "skill" or "kb"
    matched: bool
    argument_valid: bool
    argument_errors: List[str]
    result_preview: str
    timestamp_ms: int


@dataclass
class CallRecorder:
    calls: List[RecordedToolCall] = field(default_factory=list)

    def tool_names_called(self) -> List[str]:
        return [c.tool_name for c in self.calls]

    def unmatched_count(self) -> int:
        return sum(1 for c in self.calls if not c.matched)

    def invalid_argument_count(self) -> int:
        return sum(1 for c in self.calls if not c.argument_valid)


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tool_requires_datasource(tool_name: str) -> bool:
    if tool_name in {"list_documents", "read_document", "get_current_time"}:
        return False
    if tool_name in OS_CONTEXT_TOOLS:
        return False
    if tool_name.startswith(("mysql_", "pg_", "mssql_", "oracle_", "opengauss_", "hana_")):
        return True
    return tool_name in {
        "execute_diagnostic_query",
        "execute_any_sql",
        "diagnose_datasource_connection",
        "get_metric_history",
        "query_monitoring_history",
        "query_inspection_reports",
        "query_monitoring_data",
        "trigger_inspection",
    }


def validate_tool_arguments(case: EvalCase, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate that the AI scoped tool calls to the case's virtual assets."""
    args = arguments or {}
    errors: List[str] = []
    expected_datasource_id = case.context.datasource.id
    expected_host_id = case.context.host.id if case.context.host else None
    provided_datasource_id = _coerce_int(args.get("datasource_id"))
    provided_host_id = _coerce_int(args.get("host_id"))

    if tool_name in OS_CONTEXT_TOOLS:
        if provided_datasource_id is None and provided_host_id is None:
            errors.append("missing datasource_id or host_id")
        if provided_datasource_id is not None and provided_datasource_id != expected_datasource_id:
            errors.append(f"datasource_id {provided_datasource_id} != expected {expected_datasource_id}")
        if provided_host_id is not None and expected_host_id is None:
            errors.append("host_id provided but case has no virtual host")
        if provided_host_id is not None and expected_host_id is not None and provided_host_id != expected_host_id:
            errors.append(f"host_id {provided_host_id} != expected {expected_host_id}")
        return not errors, errors

    if _tool_requires_datasource(tool_name):
        if provided_datasource_id is None:
            errors.append("missing datasource_id")
        elif provided_datasource_id != expected_datasource_id:
            errors.append(f"datasource_id {provided_datasource_id} != expected {expected_datasource_id}")

    return not errors, errors


def invalid_argument_response(tool_name: str, argument_errors: List[str]) -> str:
    import json

    return json.dumps(
        {
            "success": False,
            "error": "invalid_evaluation_tool_arguments",
            "tool": tool_name,
            "argument_errors": argument_errors,
        },
        ensure_ascii=False,
    )


def make_mock_override(case: EvalCase, recorder: CallRecorder):
    """Build a coroutine compatible with `tool_override.ToolOverride`."""

    async def _override(tool_name: str, arguments: Dict[str, Any], kind: str):
        ts = int(time.time() * 1000)
        argument_valid, argument_errors = validate_tool_arguments(case, tool_name, arguments or {})
        rule = find_fixture(case.fixtures, tool_name, arguments or {}) if argument_valid else None
        if not argument_valid:
            result_str = invalid_argument_response(tool_name, argument_errors)
            matched = False
        elif rule is not None:
            result_str = render_response(rule)
            matched = True
        else:
            result_str = fallback_response(tool_name, arguments or {})
            matched = False

        recorder.calls.append(
            RecordedToolCall(
                tool_name=tool_name,
                args=dict(arguments or {}),
                kind=kind,
                matched=matched,
                argument_valid=argument_valid,
                argument_errors=argument_errors,
                result_preview=result_str[:500],
                timestamp_ms=ts,
            )
        )
        # (result_str, exec_ms, visualization)
        return result_str, 1, None

    return _override
