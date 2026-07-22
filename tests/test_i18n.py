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
    normalize_locale,
    parse_accept_language,
    translate,
)
from backend.migrations import add_user_locale
from backend.routers.auth import router as auth_router


def test_locale_normalization_and_accept_language_priority():
    assert normalize_locale("zh_Hans") == "zh-CN"
    assert normalize_locale("EN-us") == "en-US"
    assert normalize_locale("fr-FR") is None
    assert parse_accept_language("fr-FR, en-US;q=0.8, zh-CN;q=0.9") == "zh-CN"
    assert parse_accept_language("en;q=0.7, zh;q=0.2") == "en-US"
    assert parse_accept_language(None) is None


def test_translate_interpolation_and_fallback():
    assert translate("en-US", "datasource.not_found") == "Datasource not found"
    assert translate("zh-CN", "upload.too_large", {"max_size": "10MB"}) == "文件过大（最大 10MB）"
    assert translate("fr-FR", "auth.not_authenticated") == "请先登录"
    assert DEFAULT_LOCALE == "zh-CN"


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
    response = TestClient(app).put("/api/auth/me/locale", json={"locale": "en-US"})
    assert response.status_code == 200
    assert response.json()["locale"] == "en-US"
    assert user.locale == "en-US"
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


def test_app_localizes_typed_and_legacy_errors():
    app = create_app()

    @app.get("/api/_test/typed-error")
    async def typed_error():
        raise ApiError(404, "datasource.not_found", {"datasource_id": 12})

    @app.get("/api/_test/legacy-error")
    async def legacy_error():
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

    legacy = client.get("/api/_test/legacy-error", headers={"X-DBClaw-Locale": "en-US"})
    assert legacy.status_code == 404
    assert legacy.json()["detail"] == "Host not found"
    assert legacy.json()["error_code"] == "host.not_found"


@pytest.mark.parametrize("locale,expected", [("zh-CN", "字段为必填项"), ("en-US", "Field required")])
def test_app_localizes_validation_errors(locale, expected):
    app = create_app()
    client = TestClient(app)
    response = client.post("/api/auth/login", json={}, headers={"X-DBClaw-Locale": locale})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "request.validation_error"
    assert body["detail"][0]["msg"] == expected
    assert response.headers["content-language"] == locale
