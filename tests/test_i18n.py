import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.i18n.errors import ApiError
from backend.i18n.locale import (
    DEFAULT_LOCALE,
    DEFAULT_TIMEZONE,
    MESSAGES,
    normalize_locale,
    normalize_timezone,
    parse_accept_language,
    resolve_preferences,
    set_system_defaults,
    translate,
)
from backend.migrations import add_i18n_metadata, add_user_locale
from backend.routers.auth import router as auth_router
from backend.services.dingtalk_bot_service import _build_approval_prompt
from backend.services.feishu_bot_service import _build_approval_card
from backend.utils.datetime_helper import format_in_timezone


def test_locale_normalization_and_accept_language_priority():
    assert normalize_locale("zh_Hans") == "zh-CN"
    assert normalize_locale("EN-us") == "en-US"
    assert normalize_locale("fr-FR") is None
    assert parse_accept_language("fr-FR, en-US;q=0.8, zh-CN;q=0.9") == "zh-CN"
    assert parse_accept_language("en;q=0.7, zh;q=0.2") == "en-US"
    assert parse_accept_language(None) is None
    assert normalize_timezone("America/New_York") == "America/New_York"
    assert normalize_timezone("not/a-zone") is None
    assert DEFAULT_TIMEZONE == "Asia/Shanghai"


def test_translate_interpolation_and_fallback():
    assert translate("en-US", "datasource.not_found") == "Datasource not found"
    assert translate("zh-CN", "upload.too_large", {"max_size": "10MB"}) == "文件过大（最大 10MB）"
    assert translate("fr-FR", "auth.not_authenticated") == "请先登录"
    assert DEFAULT_LOCALE == "zh-CN"


def test_backend_catalogs_have_identical_keys_and_parameters():
    assert set(MESSAGES["zh-CN"]) == set(MESSAGES["en-US"])
    placeholder = re.compile(r"\{([A-Za-z0-9_]+)\}")
    for key, chinese in MESSAGES["zh-CN"].items():
        assert sorted(placeholder.findall(chinese)) == sorted(
            placeholder.findall(MESSAGES["en-US"][key])
        ), key


def test_bot_approval_surfaces_render_for_recipient_locale():
    event = {
        "approval_id": "approval-42",
        "tool_name": "Bash",
        "risk_level": "high",
        "summary": "Review the operation before it runs.",
        "risk_reason": "It changes server state.",
        "plan_markdown": "1. Run the command",
    }

    prompt = _build_approval_prompt(event, "en-US")
    assert "Confirmation required: Bash" in prompt
    assert "Risk level: High" in prompt
    assert "approve approval-42" in prompt
    assert not re.search(r"[\u3400-\u9fff]", prompt)

    card = _build_approval_card(event, 7, "en-US")
    rendered = str(card)
    assert "Confirmation required: Bash" in rendered
    assert "Approve" in rendered
    assert "Reject" in rendered
    assert not re.search(r"[\u3400-\u9fff]", rendered)


def test_registry_backed_system_defaults_are_used_for_background_preferences():
    try:
        set_system_defaults("en-US", "America/New_York")
        assert resolve_preferences() == ("en-US", "America/New_York")
    finally:
        set_system_defaults(DEFAULT_LOCALE, DEFAULT_TIMEZONE)


def test_iana_timezone_formatting_observes_dst_boundaries():
    before = datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc)
    after = datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc)
    assert format_in_timezone(before, "America/New_York") == "2026-03-08 01:30:00"
    assert format_in_timezone(after, "America/New_York") == "2026-03-08 03:30:00"


def test_language_endpoint_persists_account_preference():
    app = FastAPI()
    app.include_router(auth_router)
    user = SimpleNamespace(
        id=1,
        username="admin",
        display_name=None,
        email=None,
        phone=None,
        locale="zh-CN",
        timezone="Asia/Shanghai",
        is_active=True,
        is_admin=True,
        created_at=None,
        updated_at=None,
    )
    db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    response = TestClient(app).put(
        "/api/auth/me/locale",
        json={"locale": "en-US", "timezone": "America/New_York"},
    )
    assert response.status_code == 200
    assert response.json()["locale"] == "en-US"
    assert user.locale == "en-US"
    assert user.timezone == "America/New_York"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(user)


def test_language_endpoint_rejects_unsupported_locale():
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)

    async def override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db
    response = TestClient(app).put("/api/auth/me/locale", json={"locale": "fr-FR"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_user_locale_migration_is_safe_to_repeat(monkeypatch):
    statements = []

    class Connection:
        async def execute(self, statement):
            statements.append(str(statement))

    class Transaction:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Transaction()

    monkeypatch.setattr(add_user_locale, "get_engine", lambda: Engine())
    await add_user_locale.upgrade()
    await add_user_locale.upgrade()

    assert len(statements) == 8
    assert all("ADD COLUMN IF NOT EXISTS" in statement for statement in (statements[0], statements[4]))
    assert all("SET locale = 'zh-CN'" in statement for statement in (statements[1], statements[5]))


@pytest.mark.asyncio
async def test_i18n_metadata_migration_is_additive_and_repeatable(monkeypatch):
    statements = []

    class Connection:
        async def execute(self, statement):
            statements.append(str(statement))

    class Transaction:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Transaction()

    monkeypatch.setattr(add_i18n_metadata, "get_engine", lambda: Engine())
    await add_i18n_metadata.upgrade()
    first_run = list(statements)
    await add_i18n_metadata.upgrade()

    assert statements[:len(first_run)] == statements[len(first_run):]
    assert any("ADD COLUMN IF NOT EXISTS timezone" in item for item in first_run)
    assert any("generation_locale" in item for item in first_run)
    assert any("message_code" in item for item in first_run)
    assert any("ON CONFLICT (key) DO NOTHING" in item for item in first_run)


def test_app_localizes_typed_errors_and_safely_degrades_framework_errors():
    app = create_app()

    @app.get("/api/_test/typed-error")
    async def typed_error():
        raise ApiError(404, "datasource.not_found", {"datasource_id": 12})

    @app.get("/api/_test/framework-error")
    async def framework_error():
        raise HTTPException(404, "主机不存在")

    client = TestClient(app)
    typed = client.get("/api/_test/typed-error", headers={"X-DBClaw-Locale": "en-US"})
    assert typed.status_code == 404
    assert typed.headers["content-language"] == "en-US"
    assert typed.json() == {
        "detail": "Datasource not found",
        "error_code": "datasource.not_found",
        "params": {"datasource_id": 12},
    }

    framework = client.get("/api/_test/framework-error", headers={"X-DBClaw-Locale": "en-US"})
    assert framework.status_code == 404
    assert framework.json()["detail"] == "Request failed"
    assert framework.json()["error_code"] == "request.failed"
    assert framework.json()["debug_id"]
    assert "主机不存在" not in framework.text


def test_app_never_exposes_unmapped_or_unhandled_exception_text():
    app = create_app()

    @app.get("/api/_test/unmapped-error")
    async def unmapped_error():
        raise HTTPException(400, "vendor secret token=abc")

    @app.get("/api/_test/unhandled-error")
    async def unhandled_error():
        raise RuntimeError("database password=secret")

    client = TestClient(app, raise_server_exceptions=False)
    unmapped = client.get("/api/_test/unmapped-error", headers={"X-DBClaw-Locale": "en-US"})
    assert unmapped.json()["detail"] == "Request failed"
    assert unmapped.json()["error_code"] == "request.failed"
    assert unmapped.json()["debug_id"]
    assert "secret" not in unmapped.text

    unhandled = client.get("/api/_test/unhandled-error", headers={"X-DBClaw-Locale": "en-US"})
    assert unhandled.json()["detail"] == "Internal server error"
    assert unhandled.json()["error_code"] == "request.internal_error"
    assert unhandled.json()["debug_id"]
    assert "secret" not in unhandled.text


@pytest.mark.parametrize("locale,expected", [("zh-CN", "字段为必填项"), ("en-US", "Field required")])
def test_app_localizes_validation_errors(locale, expected):
    app = create_app()
    client = TestClient(app)
    response = client.post("/api/auth/login", json={}, headers={"X-DBClaw-Locale": locale})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "request.validation_error"
    assert body["detail"][0]["msg"] == expected
    assert body["detail"][0]["error_code"] == "request.validation.missing"
    assert response.headers["content-language"] == locale
