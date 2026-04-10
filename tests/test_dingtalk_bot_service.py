import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services import dingtalk_bot_service


def _build_integration(code: str | None = None):
    return SimpleNamespace(
        id=1,
        code=code or 'CLIENT_ID = "ding_client"\nCLIENT_SECRET = "ding_secret"\n',
        enabled=True,
    )


@pytest.mark.asyncio
async def test_extract_dingtalk_bot_config_supports_app_key_alias():
    integration = _build_integration('APP_KEY = "app_key_123"\nAPP_SECRET = "app_secret_456"\n')

    config = dingtalk_bot_service._extract_dingtalk_bot_config(integration)

    assert config["client_id"] == "app_key_123"
    assert config["client_secret"] == "app_secret_456"


@pytest.mark.asyncio
async def test_handle_message_replies_with_text_approval_prompt(monkeypatch):
    db = MagicMock()
    integration = _build_integration()
    binding = SimpleNamespace(session_id=321)

    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "is_duplicate_event", AsyncMock(return_value=False))
    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "get_bot_integration", AsyncMock(return_value=integration))
    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "get_or_create_binding", AsyncMock(return_value=binding))
    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "mark_event_processed", AsyncMock())
    monkeypatch.setattr(
        dingtalk_bot_service,
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

    monkeypatch.setattr(dingtalk_bot_service, "process_stream_events", fake_process_stream_events)

    send_reply = AsyncMock()
    payload = {
        "msgId": "msg_001",
        "conversationId": "cid_001",
        "conversationType": "2",
        "conversationTitle": "DBA 群",
        "senderId": "user_001",
        "senderStaffId": "staff_001",
        "isInAtList": True,
        "text": {"content": "帮我重启数据库"},
    }

    result = await dingtalk_bot_service.DingTalkBotService.handle_message(
        db,
        message=payload,
        send_reply=send_reply,
    )

    assert result["ok"] is True
    reply_text = send_reply.await_args.args[0]
    assert "审批ID：approval_001" in reply_text
    assert "批准 approval_001" in reply_text
    assert "拒绝 approval_001" in reply_text


@pytest.mark.asyncio
async def test_handle_message_approval_command_replies_with_followup_result(monkeypatch):
    db = MagicMock()
    integration = _build_integration()
    binding = SimpleNamespace(session_id=654)

    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "is_duplicate_event", AsyncMock(return_value=False))
    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "get_bot_integration", AsyncMock(return_value=integration))
    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "get_or_create_binding", AsyncMock(return_value=binding))
    monkeypatch.setattr(dingtalk_bot_service.DingTalkBotService, "mark_event_processed", AsyncMock())
    prepare_mock = AsyncMock(return_value=([], None, None, None, None, None))
    monkeypatch.setattr(dingtalk_bot_service, "prepare_user_turn", prepare_mock)

    async def fake_resolve_pending_approval(*args, **kwargs):
        on_event = kwargs["on_event"]
        await on_event({"type": "content", "content": "执行完成，数据库已重启。"})
        return {"status": "approved"}

    monkeypatch.setattr(dingtalk_bot_service, "resolve_pending_approval", fake_resolve_pending_approval)

    send_reply = AsyncMock()
    payload = {
        "msgId": "msg_002",
        "conversationId": "cid_002",
        "conversationType": "1",
        "senderId": "user_002",
        "senderStaffId": "staff_002",
        "text": {"content": "批准 approval_123"},
    }

    result = await dingtalk_bot_service.DingTalkBotService.handle_message(
        db,
        message=payload,
        send_reply=send_reply,
    )

    assert result["ok"] is True
    send_reply.assert_awaited_once_with("执行完成，数据库已重启。")
    prepare_mock.assert_not_awaited()
