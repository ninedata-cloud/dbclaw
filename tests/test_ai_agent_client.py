from backend.services.ai_agent import get_ai_client


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
