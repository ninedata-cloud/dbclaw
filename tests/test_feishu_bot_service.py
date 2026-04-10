import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services import feishu_bot_service


def _mock_scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _build_integration(app_id: str = "app_123", app_secret: str = "secret_123"):
    code = (
        f'APP_ID = "{app_id}"\n'
        f'APP_SECRET = "{app_secret}"\n'
        'SIGNING_SECRET = ""\n'
    )
    return SimpleNamespace(id=1, code=code, enabled=True)


@pytest.mark.asyncio
async def test_handle_message_event_sends_approval_card_and_prompt(monkeypatch):
    db = MagicMock()
    integration = _build_integration()
    binding = SimpleNamespace(session_id=321)

    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "is_duplicate_event", AsyncMock(return_value=False))
    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "get_bot_integration", AsyncMock(return_value=integration))
    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "get_or_create_binding", AsyncMock(return_value=binding))
    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "mark_event_processed", AsyncMock())
    monkeypatch.setattr(
        feishu_bot_service,
        "prepare_user_turn",
        AsyncMock(return_value=([], None, None, None, None, None)),
    )

    async def fake_process_stream_events(*args, **kwargs):
        on_event = kwargs["on_event"]
        await on_event(
            {
                "type": "approval_request",
                "approval_id": "approval_001",
                "tool_name": "execute_os_command",
                "summary": "需要确认后再执行。",
                "plan_markdown": "1. 执行命令\n2. 检查结果",
                "risk_level": "high",
                "risk_reason": "该操作会修改主机状态。",
            }
        )
        return "", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, True

    monkeypatch.setattr(feishu_bot_service, "process_stream_events", fake_process_stream_events)

    reply_mock = AsyncMock()
    card_mock = AsyncMock()
    monkeypatch.setattr(feishu_bot_service, "_reply_normal_message", reply_mock)
    monkeypatch.setattr(feishu_bot_service.feishu_service, "send_interactive_card", card_mock)

    payload = {
        "header": {"event_id": "evt_001", "event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "chat_001",
                "message_id": "msg_001",
                "content": '{"text":"帮我重启数据库"}',
            },
            "sender": {"sender_id": {"open_id": "ou_001"}},
        },
    }

    result = await feishu_bot_service.FeishuBotService.handle_message_event(db, payload)

    assert result["ok"] is True
    card_mock.assert_awaited_once()
    reply_texts = [call.kwargs["text"] for call in reply_mock.await_args_list]
    assert "收到，正在分析你的需求。" in reply_texts
    assert "请在上面的卡片中确认是否执行该操作。" in reply_texts


@pytest.mark.asyncio
async def test_handle_message_event_replies_with_error_when_stream_fails(monkeypatch):
    db = MagicMock()
    integration = _build_integration()
    binding = SimpleNamespace(session_id=654)

    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "is_duplicate_event", AsyncMock(return_value=False))
    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "get_bot_integration", AsyncMock(return_value=integration))
    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "get_or_create_binding", AsyncMock(return_value=binding))
    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "mark_event_processed", AsyncMock())
    monkeypatch.setattr(
        feishu_bot_service,
        "prepare_user_turn",
        AsyncMock(return_value=([], None, None, None, None, None)),
    )

    async def fake_process_stream_events(*args, **kwargs):
        on_event = kwargs["on_event"]
        await on_event({"type": "error", "content": "上游模型当前不可用，请稍后再试。"})
        return "", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, False

    monkeypatch.setattr(feishu_bot_service, "process_stream_events", fake_process_stream_events)

    reply_mock = AsyncMock()
    card_mock = AsyncMock()
    monkeypatch.setattr(feishu_bot_service, "_reply_normal_message", reply_mock)
    monkeypatch.setattr(feishu_bot_service.feishu_service, "send_interactive_card", card_mock)

    payload = {
        "header": {"event_id": "evt_002", "event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "chat_002",
                "message_id": "msg_002",
                "content": '{"text":"帮我分析一下"}',
            },
            "sender": {"sender_id": {"open_id": "ou_002"}},
        },
    }

    result = await feishu_bot_service.FeishuBotService.handle_message_event(db, payload)

    assert result["ok"] is True
    card_mock.assert_not_awaited()
    reply_texts = [call.kwargs["text"] for call in reply_mock.await_args_list]
    assert "收到，正在分析你的需求。" in reply_texts
    assert "上游模型当前不可用，请稍后再试。" in reply_texts


@pytest.mark.asyncio
async def test_handle_action_event_prompts_for_followup_approval(monkeypatch):
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _mock_scalar_result(SimpleNamespace(external_chat_id="chat_003")),
        ]
    )
    integration = _build_integration()

    monkeypatch.setattr(feishu_bot_service.FeishuBotService, "get_bot_integration", AsyncMock(return_value=integration))

    async def fake_resolve_pending_approval(*args, **kwargs):
        on_event = kwargs["on_event"]
        await on_event(
            {
                "type": "approval_request",
                "approval_id": "approval_next",
                "tool_name": "execute_any_os_command",
                "summary": "还需要继续确认。",
                "plan_markdown": "1. 执行下一步",
                "risk_level": "high",
                "risk_reason": "后续动作仍有风险。",
            }
        )
        return {"status": "approved"}

    monkeypatch.setattr(feishu_bot_service, "resolve_pending_approval", fake_resolve_pending_approval)

    reply_mock = AsyncMock()
    card_mock = AsyncMock()
    monkeypatch.setattr(feishu_bot_service, "_reply_normal_message", reply_mock)
    monkeypatch.setattr(feishu_bot_service.feishu_service, "send_interactive_card", card_mock)

    payload = {
        "header": {"event_type": "card.action.trigger"},
        "action": {
            "value": {
                "session_id": "777",
                "approval_id": "approval_current",
                "action": "approved",
            }
        },
        "operator": {"operator_id": {"open_id": "ou_003"}},
        "open_message_id": "open_msg_003",
    }

    result = await feishu_bot_service.FeishuBotService.handle_action_event(db, payload)

    card_mock.assert_awaited_once()
    reply_texts = [call.kwargs["text"] for call in reply_mock.await_args_list]
    assert "后续还有高风险操作，请继续在新卡片中确认。" in reply_texts
    assert result["toast"]["content"] == "已批准执行，请继续确认后续操作。"
