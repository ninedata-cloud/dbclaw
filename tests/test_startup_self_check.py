#!/usr/bin/env python3
"""启动自检最小回归测试。"""
import asyncio
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "postgresql+asyncpg://dbclaw:test-pass@127.0.0.1:5432/dbclaw"
os.environ["ENCRYPTION_KEY"] = "4WEqnK34-IxW8xugCJ8SrLw6VHgxHpM5LOAQWAxPd1c="
os.environ["PUBLIC_SHARE_SECRET_KEY"] = "test-public-share-secret-1234567890"
os.environ["INITIAL_ADMIN_PASSWORD"] = "admin1234"
os.environ["APP_PORT"] = "19939"
os.environ["DEBUG"] = "false"

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_settings

get_settings.cache_clear()

import backend.services.startup_self_check as startup_self_check


class _FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return statement


class _FakeEngine:
    def connect(self):
        return _FakeConnection()

    async def dispose(self):
        return None


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


async def _fake_probe_postgres_endpoint(host: str, port: int, database: str):
    del host, port, database
    return None


async def main():
    settings = get_settings()

    original_probe = startup_self_check._probe_postgres_endpoint
    original_create_engine = startup_self_check.create_async_engine

    startup_self_check._probe_postgres_endpoint = _fake_probe_postgres_endpoint
    startup_self_check.create_async_engine = lambda *args, **kwargs: _FakeEngine()

    try:
        startup_report = await startup_self_check.run_startup_self_check(settings, include_app_port_check=True)
        assert_true(startup_report.ok, startup_report.to_console_text(include_passes=True))
        assert_true(startup_report.warning_count == 1, f"expected 1 warning, got {startup_report.warning_count}")
        assert_true(
            any(check.name == "INITIAL_ADMIN_PASSWORD" and check.status == "warn" for check in startup_report.checks),
            "default admin password warning missing",
        )

        readiness_report = await startup_self_check.run_readiness_self_check(settings)
        assert_true(readiness_report.ok, readiness_report.to_console_text(include_passes=True))

        unsupported_settings = settings.model_copy(update={"database_url": "mysql+aiomysql://user:pass@127.0.0.1:3306/dbclaw"})
        unsupported_report = await startup_self_check.run_readiness_self_check(unsupported_settings)
        assert_true(not unsupported_report.ok, "non-PostgreSQL URL should be rejected")
        assert_true(
            any("不支持的元数据库驱动" in check.summary for check in unsupported_report.checks),
            unsupported_report.to_console_text(include_passes=True),
        )
    finally:
        startup_self_check._probe_postgres_endpoint = original_probe
        startup_self_check.create_async_engine = original_create_engine

    print("startup self-check tests passed")


if __name__ == "__main__":
    asyncio.run(main())
