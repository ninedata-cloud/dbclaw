import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.ai_agent import get_ai_client
from backend.services.ai_agent import AIClient, _stream_openai_turn
from backend.services.chat_orchestration_service import rebuild_llm_messages, _emit


def test_openai_compatible_client_uses_app_user_agent_for_custom_gateway(mocker):
    async_openai = mocker.patch("backend.services.ai_agent.AsyncOpenAI")
    async_client = mocker.patch("backend.services.ai_agent.httpx.AsyncClient")

    get_ai_client(
        api_key="sk-test",
        base_url="https://api.86gamestore.com/v1",
        model_name="gpt-5.5",
        protocol="openai",
    )

    async_client.assert_called_once_with(headers={"User-Agent": "DBClaw/1.0"})
    async_openai.assert_called_once()
    assert async_openai.call_args.kwargs["default_headers"] == {"User-Agent": "DBClaw/1.0"}
    assert async_openai.call_args.kwargs["http_client"] == async_client.return_value


def test_official_openai_client_keeps_sdk_defaults(mocker):
    async_openai = mocker.patch("backend.services.ai_agent.AsyncOpenAI")
    async_client = mocker.patch("backend.services.ai_agent.httpx.AsyncClient")

    get_ai_client(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model_name="gpt-5.5",
        protocol="openai",
    )

    async_client.assert_not_called()
    assert "default_headers" not in async_openai.call_args.kwargs
    assert "http_client" not in async_openai.call_args.kwargs


@pytest.mark.asyncio
async def test_openai_stream_round_trips_deepseek_reasoning_content():
    async def chunks():
        yield SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None, model_extra={"reasoning_content": "先分析"}),
                    finish_reason=None,
                )
            ],
        )
        yield SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_1",
                                function=SimpleNamespace(
                                    name="get_os_metrics",
                                    arguments='{"host_id": 1}',
                                ),
                            )
                        ],
                        model_extra={},
                    ),
                    finish_reason="tool_calls",
                )
            ],
        )

    create = AsyncMock(return_value=chunks())
    client = AIClient(
        protocol="openai",
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com",
    )

    events = [
        event
        async for event in _stream_openai_turn(
            client,
            [{"role": "user", "content": "诊断主机"}],
            tools=[],
        )
    ]

    assert events[-1]["type"] == "message_complete"
    assert events[-1]["reasoning_content"] == "先分析"
    assert events[-1]["tool_calls"][0]["function"]["name"] == "get_os_metrics"


@pytest.mark.asyncio
async def test_rebuild_llm_messages_restores_tool_call_reasoning_content():
    stored_tool_call = SimpleNamespace(
        id=1,
        role="tool_call",
        content=json.dumps({
            "tool_name": "get_os_metrics",
            "tool_args": {"host_id": 1},
            "tool_call_id": "call_1",
            "reasoning_content": "需要先读取主机指标",
        }),
        tool_call_id="call_1",
        tool_calls=None,
        attachments=None,
    )

    messages = await rebuild_llm_messages([stored_tool_call])

    assert messages == [{
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "get_os_metrics",
                "arguments": '{"host_id": 1}',
            },
        }],
        "reasoning_content": "需要先读取主机指标",
    }]


@pytest.mark.asyncio
async def test_emit_hides_internal_reasoning_content():
    captured = []

    async def on_event(event):
        captured.append(event)

    await _emit({"type": "approval_request", "reasoning_content": "内部推理"}, on_event)

    assert captured == [{"type": "approval_request"}]
