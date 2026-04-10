import sys
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services import feishu_longconn_service
from backend.services.feishu_longconn_service import (
    _normalize_action_event,
    _normalize_message_event,
    _sanitize_log_message,
    _configure_lark_logger,
    _SensitiveLogFilter,
)


class _DummySessionContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_normalize_message_event_maps_sdk_model_to_existing_payload_shape():
    data = SimpleNamespace(
        header=SimpleNamespace(event_id="evt_123", event_type="im.message.receive_v1"),
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="ou_123", user_id="u_123", union_id="un_123"),
                sender_type="user",
                tenant_key="tenant_123",
            ),
            message=SimpleNamespace(
                chat_id="chat_123",
                message_id="msg_123",
                message_type="text",
                content='{"text":"你好"}',
                chat_type="p2p",
                mentions=[],
            ),
        ),
    )

    payload = _normalize_message_event(data)

    assert payload["header"]["event_id"] == "evt_123"
    assert payload["header"]["event_type"] == "im.message.receive_v1"
    assert payload["event"]["sender"]["sender_id"]["open_id"] == "ou_123"
    assert payload["event"]["message"]["chat_id"] == "chat_123"
    assert payload["event"]["message"]["content"] == '{"text":"你好"}'


def test_normalize_action_event_maps_sdk_model_to_existing_payload_shape():
    data = SimpleNamespace(
        header=SimpleNamespace(event_id="evt_456", event_type="card.action.trigger"),
        event=SimpleNamespace(
            operator=SimpleNamespace(open_id="ou_action", user_id="u_action", union_id="un_action"),
            action=SimpleNamespace(
                tag="button",
                value={"session_id": "100", "approval_id": "ap_1", "action": "approved"},
                form_value={"comment": "ok"},
                input_value="input",
                option="A",
                timezone="Asia/Shanghai",
                name="approve-btn",
                options=["A", "B"],
                checked=True,
            ),
            context=SimpleNamespace(open_message_id="om_123"),
        ),
    )

    payload = _normalize_action_event(data)

    assert payload["header"]["event_id"] == "evt_456"
    assert payload["header"]["event_type"] == "card.action.trigger"
    assert payload["action"]["value"]["approval_id"] == "ap_1"
    assert payload["action"]["form_value"]["comment"] == "ok"
    assert payload["operator"]["operator_id"]["open_id"] == "ou_action"
    assert payload["open_message_id"] == "om_123"


def test_sanitize_log_message_redacts_url_query_string():
    message = (
        "connected to "
        "wss://msg-frontier.feishu.cn/ws/v2?fpid=493&aid=552564&device_id=7626756120875584443"
        "&access_key=secret&service_id=33554678&ticket=sensitive-token [conn_id=7626756120875584443]"
    )

    sanitized = _sanitize_log_message(message)

    assert "access_key=secret" not in sanitized
    assert "ticket=sensitive-token" not in sanitized
    assert "device_id=7626756120875584443&access_key=secret" not in sanitized
    assert "wss://msg-frontier.feishu.cn/ws/v2?redacted" in sanitized
    assert "[conn_id=7626756120875584443]" in sanitized


def test_configure_lark_logger_disables_propagation_and_adds_filter_once():
    sdk_logger = logging.getLogger("Lark")
    original_level = sdk_logger.level
    original_propagate = sdk_logger.propagate
    original_filters = list(sdk_logger.filters)

    try:
        for log_filter in list(sdk_logger.filters):
            if isinstance(log_filter, _SensitiveLogFilter):
                sdk_logger.removeFilter(log_filter)

        sdk_logger.propagate = True
        _configure_lark_logger(logging.WARNING)
        _configure_lark_logger(logging.WARNING)

        assert sdk_logger.level == logging.WARNING
        assert sdk_logger.propagate is False
        assert sum(isinstance(log_filter, _SensitiveLogFilter) for log_filter in sdk_logger.filters) == 1
    finally:
        sdk_logger.filters = original_filters
        sdk_logger.propagate = original_propagate
        sdk_logger.setLevel(original_level)


@pytest.mark.asyncio
async def test_start_feishu_longconn_client_marks_error_when_sdk_missing(monkeypatch):
    feishu_longconn_service._WS_THREAD = None
    feishu_longconn_service._WS_STOP_EVENT = None
    feishu_longconn_service._APP_LOOP = None

    monkeypatch.setattr(feishu_longconn_service, "async_session", lambda: _DummySessionContext())
    monkeypatch.setattr(
        feishu_longconn_service.FeishuBotService,
        "get_bot_integration",
        AsyncMock(return_value=SimpleNamespace(id=1, code='APP_ID = "app"\nAPP_SECRET = "secret"\n', enabled=True)),
    )
    monkeypatch.setattr(feishu_longconn_service.FeishuBotService, "ensure_bot_binding", AsyncMock())
    status_mock = AsyncMock()
    monkeypatch.setattr(feishu_longconn_service, "_update_binding_status", status_mock)
    monkeypatch.setattr(feishu_longconn_service.importlib.util, "find_spec", lambda name: None)

    await feishu_longconn_service.start_feishu_longconn_client()

    status_mock.assert_awaited_once()
    assert status_mock.await_args.kwargs["login_status"] == "error"
    assert "lark-oapi" in status_mock.await_args.kwargs["last_error"]


@pytest.mark.asyncio
async def test_start_feishu_longconn_client_marks_not_ready_when_credentials_missing(monkeypatch):
    feishu_longconn_service._WS_THREAD = None
    feishu_longconn_service._WS_STOP_EVENT = None
    feishu_longconn_service._APP_LOOP = None

    monkeypatch.setattr(feishu_longconn_service, "async_session", lambda: _DummySessionContext())
    monkeypatch.setattr(
        feishu_longconn_service.FeishuBotService,
        "get_bot_integration",
        AsyncMock(return_value=SimpleNamespace(id=1, code='APP_ID = ""\nAPP_SECRET = ""\n', enabled=True)),
    )
    monkeypatch.setattr(feishu_longconn_service.FeishuBotService, "ensure_bot_binding", AsyncMock())
    status_mock = AsyncMock()
    monkeypatch.setattr(feishu_longconn_service, "_update_binding_status", status_mock)
    monkeypatch.setattr(feishu_longconn_service.importlib.util, "find_spec", lambda name: object())

    await feishu_longconn_service.start_feishu_longconn_client()

    status_mock.assert_awaited_once_with(login_status="not_ready", last_error="")
