import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services import chat_orchestration_service
from backend.utils.datetime_helper import now


def _mock_messages_result(messages):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = messages
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_load_session_messages_for_llm_filters_history_by_hours():
    current = now()
    recent_msg = SimpleNamespace(created_at=current - timedelta(hours=2), content="recent")
    old_msg = SimpleNamespace(created_at=current - timedelta(days=2), content="old")
    no_time_msg = SimpleNamespace(created_at=None, content="no_time")

    db = MagicMock()
    db.execute = AsyncMock(return_value=_mock_messages_result([old_msg, recent_msg, no_time_msg]))

    messages = await chat_orchestration_service.load_session_messages_for_llm(
        db,
        session_id=1,
        history_window_hours=24,
    )

    assert recent_msg in messages
    assert no_time_msg in messages
    assert old_msg not in messages
    query_text = str(db.execute.await_args.args[0])
    assert "ORDER BY chat_messages.id" in query_text


@pytest.mark.asyncio
async def test_resolve_pending_approval_keeps_history_window_for_resume(monkeypatch):
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    monkeypatch.setattr(chat_orchestration_service, "_emit", AsyncMock())
    monkeypatch.setattr(chat_orchestration_service, "_store_tool_call", AsyncMock())
    monkeypatch.setattr(
        chat_orchestration_service,
        "execute_skill_call",
        AsyncMock(return_value=('{"success": true}', 12, None, None)),
    )
    monkeypatch.setattr(chat_orchestration_service, "_store_tool_result", AsyncMock())
    resume_mock = AsyncMock(return_value=("", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, False))
    monkeypatch.setattr(chat_orchestration_service, "continue_conversation_after_tool", resume_mock)

    pending_approvals = {
        10: {
            "approval_1": {
                "approval_id": "approval_1",
                "tool_name": "execute_os_command",
                "tool_args": {"command": "uptime"},
                "tool_call_id": "call_1",
                "datasource_id": None,
                "model_id": None,
                "kb_ids": None,
                "knowledge_context": None,
                "disabled_tools": None,
                "user_id": None,
                "history_window_hours": 24,
            }
        }
    }

    result = await chat_orchestration_service.resolve_pending_approval(
        db,
        session_id=10,
        approval_id="approval_1",
        action="approved",
        comment=None,
        user_id=None,
        pending_approvals=pending_approvals,
        on_event=None,
    )

    assert result["status"] == "approved"
    assert resume_mock.await_args.kwargs["history_window_hours"] == 24
