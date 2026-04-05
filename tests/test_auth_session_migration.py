#!/usr/bin/env python3
"""最小认证回归测试：Cookie 会话登录、恢复、登出、改密失效"""
import asyncio
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

# 先配置环境变量，确保后续 import 使用测试配置
_TEMP_DIR = TemporaryDirectory()
_DB_PATH = Path(_TEMP_DIR.name) / "auth_test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-1234567890"
os.environ["PUBLIC_SHARE_SECRET_KEY"] = "test-public-share-secret-1234567890"
os.environ["INITIAL_ADMIN_PASSWORD"] = "admin123456"
os.environ["SESSION_COOKIE_NAME"] = "dbguard_session"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["SESSION_COOKIE_SAMESITE"] = "lax"
os.environ["DEBUG"] = "false"

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_settings
get_settings.cache_clear()

from backend.app import create_app
from backend.database import Base, engine, async_session
from backend.models.user import User
from backend.models.login_log import LoginLog
from backend.models.user_session import UserSession
from backend.utils.security import hash_password


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


async def reset_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("admin123456"),
            display_name="Administrator",
            is_active=True,
            is_admin=True,
        )
        session.add(admin)
        await session.commit()


async def count_user_sessions() -> int:
    async with async_session() as session:
        result = await session.execute(UserSession.__table__.select())
        return len(result.fetchall())


async def get_user_session_statuses() -> list[str]:
    async with async_session() as session:
        result = await session.execute(UserSession.__table__.select().order_by(UserSession.id))
        return [row.status for row in result.fetchall()]


def run_tests() -> bool:
    print("\n认证会话迁移回归测试")
    print("=" * 60)
    results = TestResults()

    asyncio.run(reset_database())
    app = create_app()

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
            statuses = asyncio.run(get_user_session_statuses())
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

            statuses = asyncio.run(get_user_session_statuses())
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
