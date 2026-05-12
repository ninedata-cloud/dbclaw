"""Match a tool call (name + args) against a list of FixtureRule entries."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.evaluation.case_loader import FixtureRule

logger = logging.getLogger(__name__)


def _args_match(rule_args: Any, call_args: Dict[str, Any]) -> bool:
    """Match policies:
        "any"               -> always match
        {} or None          -> always match
        {"sql_pattern": r}  -> regex r searches `sql` / `query` field of call_args
        {key: value, ...}   -> all keys present and equal in call_args
    """
    if rule_args is None or rule_args == "any":
        return True
    if not isinstance(rule_args, dict):
        return False
    if not rule_args:
        return True

    if "sql_pattern" in rule_args:
        pattern = rule_args["sql_pattern"]
        sql_text = ""
        for k in ("sql", "query", "statement", "explain_sql"):
            v = call_args.get(k)
            if isinstance(v, str):
                sql_text = v
                break
        if not sql_text:
            sql_text = json.dumps(call_args, ensure_ascii=False)
        try:
            if not re.search(pattern, sql_text, re.IGNORECASE | re.DOTALL):
                return False
        except re.error as exc:
            logger.warning("Invalid sql_pattern %r: %s", pattern, exc)
            return False
        # other keys must also match exactly
        rest = {k: v for k, v in rule_args.items() if k != "sql_pattern"}
        for k, v in rest.items():
            if call_args.get(k) != v:
                return False
        return True

    for k, v in rule_args.items():
        if call_args.get(k) != v:
            return False
    return True


def find_fixture(
    fixtures: List[FixtureRule],
    tool_name: str,
    call_args: Dict[str, Any],
) -> Optional[FixtureRule]:
    for rule in fixtures:
        if rule.tool != tool_name:
            continue
        if _args_match(rule.args, call_args):
            return rule
    return None


def render_response(rule: FixtureRule) -> str:
    """Serialize a fixture response into the JSON string the AI tool layer expects."""
    response = rule.response
    if isinstance(response, str):
        return response
    return json.dumps(response, ensure_ascii=False, default=str)


def fallback_response(tool_name: str, call_args: Dict[str, Any]) -> str:
    """When no fixture matches, return a structured 'no data' result.

    We deliberately mark it as a non-error so the AI keeps working but learns
    that this tool produced no useful data — pushing it toward better tool
    selection. The runner will tally `unmatched_calls` for reporting.
    """
    return json.dumps(
        {
            "success": True,
            "data": [],
            "note": (
                f"[evaluation] no fixture matched for tool {tool_name}. "
                "This tool's output is not part of the test scenario."
            ),
        },
        ensure_ascii=False,
    )


def summarize_call(tool_name: str, call_args: Dict[str, Any]) -> Tuple[str, str]:
    """Stable id + human label for a tool call. Used for required/forbidden tallying."""
    label = tool_name
    if isinstance(call_args, dict):
        for k in ("sql", "query"):
            v = call_args.get(k)
            if isinstance(v, str):
                label = f"{tool_name}({v[:60]})"
                break
    return tool_name, label
