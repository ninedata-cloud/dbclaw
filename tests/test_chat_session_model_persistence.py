import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.diagnostic_session import DiagnosticSession
from backend.services import chat_orchestration_service


def _mock_scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_messages_result(messages):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = messages
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_prepare_user_turn_updates_existing_session_model(monkeypatch):
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    session = DiagnosticSession(
        id=101,
        user_id=7,
        datasource_id=88,
        ai_model_id=1,
        title="新建会话",
    )
    knowledge_context = {"documents": []}

    db.execute.side_effect = [
        _mock_scalar_result(session),
        _mock_messages_result([]),
    ]
    monkeypatch.setattr(
        chat_orchestration_service,
        "build_knowledge_context",
        AsyncMock(return_value=knowledge_context),
    )

    _, effective_datasource_id, effective_model_id, _, returned_knowledge_context, _ = await chat_orchestration_service.prepare_user_turn(
        db,
        session_id=101,
        user_id=7,
        user_message="数据库 CPU 很高，帮我看看",
        attachments=[],
        payload_datasource_id=None,
        model_id=2,
    )

    assert effective_datasource_id == 88
    assert session.ai_model_id == 2
    assert effective_model_id == 2
    assert session.knowledge_snapshot == knowledge_context
    assert returned_knowledge_context == knowledge_context


@pytest.mark.asyncio
async def test_prepare_user_turn_reuses_session_model_when_request_omits_model(monkeypatch):
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    session = DiagnosticSession(
        id=202,
        user_id=9,
        datasource_id=None,
        ai_model_id=6,
        title="已有会话",
    )

    db.execute.side_effect = [
        _mock_scalar_result(session),
        _mock_messages_result([]),
    ]
    monkeypatch.setattr(
        chat_orchestration_service,
        "build_knowledge_context",
        AsyncMock(return_value={"documents": []}),
    )

    _, _, effective_model_id, _, _, _ = await chat_orchestration_service.prepare_user_turn(
        db,
        session_id=202,
        user_id=9,
        user_message="继续分析刚才的问题",
        attachments=[],
        payload_datasource_id=None,
        model_id=None,
    )

    assert session.ai_model_id == 6
    assert effective_model_id == 6
