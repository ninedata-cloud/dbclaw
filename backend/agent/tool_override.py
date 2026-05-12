"""Tool execution override hook for evaluation/replay scenarios.

When set, callers in `conversation_skills.run_conversation_with_skills` will
delegate tool execution to the override callable instead of running the real
skill executor or KB tools. This lets the evaluation runner replay a fixture
without spinning up real datasources.
"""
from __future__ import annotations

import contextvars
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

# Override signature:
#   async def override(tool_name, arguments, kind) -> tuple[result_str, exec_time_ms, visualization]
# kind is "skill" or "kb".
ToolOverride = Callable[
    [str, Dict[str, Any], str],
    Awaitable[Tuple[str, int, Optional[Dict[str, Any]]]],
]

_override_var: contextvars.ContextVar[Optional[ToolOverride]] = contextvars.ContextVar(
    "tool_execution_override", default=None
)


def set_tool_override(override: Optional[ToolOverride]) -> contextvars.Token:
    """Install an override for the current async context. Returns a Token for resetting."""
    return _override_var.set(override)


def reset_tool_override(token: contextvars.Token) -> None:
    _override_var.reset(token)


def get_tool_override() -> Optional[ToolOverride]:
    return _override_var.get()
