import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services import dingtalk_stream_service


class _DummySessionContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_integration(code: str):
    return SimpleNamespace(id=1, code=code, enabled=True)


@pytest.mark.asyncio
async def test_start_dingtalk_stream_client_marks_error_when_sdk_missing(monkeypatch):
    dingtalk_stream_service._WS_THREAD = None
    dingtalk_stream_service._WS_STOP_EVENT = None
    dingtalk_stream_service._APP_LOOP = None

    monkeypatch.setattr(dingtalk_stream_service, "async_session", lambda: _DummySessionContext())
    monkeypatch.setattr(
        dingtalk_stream_service.DingTalkBotService,
        "get_bot_integration",
        AsyncMock(return_value=_build_integration('CLIENT_ID = "ding"\nCLIENT_SECRET = "secret"\n')),
    )
    monkeypatch.setattr(dingtalk_stream_service.DingTalkBotService, "ensure_bot_binding", AsyncMock())
    status_mock = AsyncMock()
    monkeypatch.setattr(dingtalk_stream_service, "_update_binding_status", status_mock)
    monkeypatch.setattr(dingtalk_stream_service.importlib.util, "find_spec", lambda name: None)

    await dingtalk_stream_service.start_dingtalk_stream_client()

    status_mock.assert_awaited_once()
    assert status_mock.await_args.kwargs["login_status"] == "error"
    assert "dingtalk-stream" in status_mock.await_args.kwargs["last_error"]


@pytest.mark.asyncio
async def test_start_dingtalk_stream_client_marks_not_ready_when_credentials_missing(monkeypatch):
    dingtalk_stream_service._WS_THREAD = None
    dingtalk_stream_service._WS_STOP_EVENT = None
    dingtalk_stream_service._APP_LOOP = None

    monkeypatch.setattr(dingtalk_stream_service, "async_session", lambda: _DummySessionContext())
    monkeypatch.setattr(
        dingtalk_stream_service.DingTalkBotService,
        "get_bot_integration",
        AsyncMock(return_value=_build_integration('CLIENT_ID = ""\nCLIENT_SECRET = ""\n')),
    )
    monkeypatch.setattr(dingtalk_stream_service.DingTalkBotService, "ensure_bot_binding", AsyncMock())
    status_mock = AsyncMock()
    monkeypatch.setattr(dingtalk_stream_service, "_update_binding_status", status_mock)
    monkeypatch.setattr(dingtalk_stream_service.importlib.util, "find_spec", lambda name: object())

    await dingtalk_stream_service.start_dingtalk_stream_client()

    status_mock.assert_awaited_once_with(login_status="not_ready", last_error="")
