#!/usr/bin/env python3
"""最小认证回归测试：Cookie 会话登录、恢复、登出、改密失效。"""
import asyncio
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

# 先配置环境变量，确保后续 import 使用测试配置
os.environ["DATABASE_URL"] = "postgresql+asyncpg://dbclaw:test-pass@127.0.0.1:5432/dbclaw"
os.environ["ENCRYPTION_KEY"] = "4WEqnK34-IxW8xugCJ8SrLw6VHgxHpM5LOAQWAxPd1c="
os.environ["PUBLIC_SHARE_SECRET_KEY"] = "test-public-share-secret-1234567890"
os.environ["INITIAL_ADMIN_PASSWORD"] = "admin123456"
os.environ["SESSION_COOKIE_NAME"] = "dbclaw_session"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["SESSION_COOKIE_SAMESITE"] = "lax"
os.environ["DEBUG"] = "false"

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_settings

get_settings.cache_clear()

from backend.database import get_db
from backend.models.login_log import LoginLog
from backend.models.user import User
from backend.models.user_session import UserSession
from backend.routers import auth
from backend.utils.security import hash_password


class FakeScalarSequence:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class FakeResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = list(values or [])

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def scalars(self):
        if self._values:
            return FakeScalarSequence(self._values)
        if self._value is None:
            return FakeScalarSequence([])
        return FakeScalarSequence([self._value])


def _extract_where_value(statement, field_name: str):
    for criterion in getattr(statement, "_where_criteria", ()):
        left = getattr(criterion, "left", None)
        right = getattr(criterion, "right", None)
        if getattr(left, "key", None) != field_name:
            continue
        if hasattr(right, "value"):
            return right.value
    return None


class FakeAuthDBSession:
    def __init__(self):
        self.user_by_id = {}
        self.user_by_username = {}
        self.sessions = []
        self.login_log = []
        self._next_login_log_id = 1
        self._next_session_id = 1

    def seed_admin(self, password: str):
        admin = User(
            id=1,
            username="admin",
            password_hash=hash_password(password),
            display_name="Administrator",
            is_active=True,
            is_admin=True,
            session_version=1,
        )
        self.user_by_id[admin.id] = admin
        self.user_by_username[admin.username] = admin

    def add(self, obj):
        if isinstance(obj, LoginLog):
            obj.id = self._next_login_log_id
            self._next_login_log_id += 1
            self.login_log.append(obj)
            return
        if isinstance(obj, UserSession):
            obj.id = self._next_session_id
            self._next_session_id += 1
            self.sessions.append(obj)
            return
        if isinstance(obj, User):
            self.user_by_id[obj.id] = obj
            self.user_by_username[obj.username] = obj

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def refresh(self, obj):
        return obj

    async def execute(self, statement):
        if isinstance(statement, Select):
            entity = statement.column_descriptions[0].get("entity")
            if entity is User:
                username = _extract_where_value(statement, "username")
                if username is not None:
                    user = self.user_by_username.get(username)
                    if user and getattr(user, "deleted_at", None) is None:
                        return FakeResult(value=user)
                    return FakeResult()

                user_id = _extract_where_value(statement, "id")
                user = self.user_by_id.get(user_id)
                if user and getattr(user, "deleted_at", None) is None:
                    return FakeResult(value=user)
                return FakeResult()

            if entity is UserSession:
                session_hash = _extract_where_value(statement, "session_id_hash")
                for session in self.sessions:
                    if session.session_id_hash == session_hash:
                        return FakeResult(value=session)
                return FakeResult()

        if isinstance(statement, Update) and statement.table.name == UserSession.__tablename__:
            user_id = _extract_where_value(statement, "user_id")
            status = _extract_where_value(statement, "status")
            values = dict(getattr(statement, "_values", {}))
            for session in self.sessions:
                if session.user_id == user_id and session.status == status:
                    for field, value in values.items():
                        key = getattr(field, "key", str(field))
                        setattr(session, key, getattr(value, "value", value))
            return FakeResult()

        raise AssertionError(f"Unexpected statement: {statement}")


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, name: str):
        self.passed += 1
        print(f"  ✓ {name}")

    def record_fail(self, name: str, error: str):
        self.failed += 1
        self.errors.append(f"{name}: {error}")
        print(f"  ✗ {name}: {error}")

    def summary(self) -> bool:
        total = self.passed + self.failed
        print(f"\nResults: {self.passed}/{total} passed")
        if self.errors:
            print("Failures:")
            for error in self.errors:
                print(f"  - {error}")
        return self.failed == 0


def build_test_app(fake_db: FakeAuthDBSession) -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router)

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    return app


def run_tests() -> bool:
    print("\n认证会话迁移回归测试")
    print("=" * 60)
    results = TestResults()

    fake_db = FakeAuthDBSession()
    fake_db.seed_admin("admin123456")
    app = build_test_app(fake_db)

    with TestClient(app) as client:
        try:
            response = client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer legacy-token-should-not-work"},
            )
            assert response.status_code == 401, response.text
            results.record_pass("不再接受 Bearer Token 作为认证凭据")
        except Exception as e:
            results.record_fail("不再接受 Bearer Token 作为认证凭据", str(e))

        try:
            response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
            assert response.status_code == 200, response.text
            data = response.json()
            assert "user" in data, data
            assert "access_token" not in data, data
            assert get_settings().session_cookie_name in client.cookies, client.cookies
            results.record_pass("登录返回 user 且设置会话 Cookie")
        except Exception as e:
            results.record_fail("登录返回 user 且设置会话 Cookie", str(e))

        try:
            response = client.get("/api/auth/me")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["username"] == "admin", data
            results.record_pass("登录后 /api/auth/me 可恢复当前用户")
        except Exception as e:
            results.record_fail("登录后 /api/auth/me 可恢复当前用户", str(e))

        try:
            response = client.post("/api/auth/logout", json={})
            assert response.status_code == 200, response.text
            response = client.get("/api/auth/me")
            assert response.status_code == 401, response.text
            statuses = [session.status for session in fake_db.sessions]
            assert statuses == ["revoked"], statuses
            results.record_pass("登出后当前会话失效")
        except Exception as e:
            results.record_fail("登出后当前会话失效", str(e))

        try:
            response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
            assert response.status_code == 200, response.text
            old_cookie = client.cookies.get(get_settings().session_cookie_name)
            assert old_cookie, client.cookies

            response = client.post(
                "/api/auth/change-password",
                json={"old_password": "admin123456", "new_password": "newpass123456"},
            )
            assert response.status_code == 200, response.text

            response = client.get("/api/auth/me")
            assert response.status_code == 401, response.text

            statuses = [session.status for session in fake_db.sessions]
            assert statuses == ["revoked", "revoked"], statuses
            results.record_pass("改密后当前 Cookie 会话被撤销")
        except Exception as e:
            results.record_fail("改密后当前 Cookie 会话被撤销", str(e))

        try:
            response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
            assert response.status_code == 401, response.text

            response = client.post("/api/auth/login", json={"username": "admin", "password": "newpass123456"})
            assert response.status_code == 200, response.text
            results.record_pass("改密后旧密码失效且新密码可登录")
        except Exception as e:
            results.record_fail("改密后旧密码失效且新密码可登录", str(e))

    return results.summary()


if __name__ == "__main__":
    ok = run_tests()
    raise SystemExit(0 if ok else 1)
