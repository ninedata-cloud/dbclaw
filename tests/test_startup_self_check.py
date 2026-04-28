from unittest.mock import AsyncMock

import pytest

from backend.config import Settings
from backend.services import startup_self_check


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_initial_admin_password_warns_when_db_password_matches_env(mocker):
    settings = Settings(initial_admin_password="StrongPass#2026")
    mocker.patch.object(
        startup_self_check,
        "_fetch_admin_password_hash",
        AsyncMock(return_value=("mock-hash", None)),
    )
    mocker.patch.object(startup_self_check, "verify_password", return_value=True)

    result = await startup_self_check._check_initial_admin_password(settings)

    assert result.status == "warn"
    assert result.name == "INITIAL_ADMIN_PASSWORD"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_initial_admin_password_passes_when_db_password_differs(mocker):
    settings = Settings(initial_admin_password="StrongPass#2026")
    mocker.patch.object(
        startup_self_check,
        "_fetch_admin_password_hash",
        AsyncMock(return_value=("mock-hash", None)),
    )
    mocker.patch.object(startup_self_check, "verify_password", return_value=False)

    result = await startup_self_check._check_initial_admin_password(settings)

    assert result.status == "pass"
    assert "不一致" in result.summary


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_initial_admin_password_passes_when_admin_absent(mocker):
    settings = Settings(initial_admin_password="StrongPass#2026")
    mocker.patch.object(
        startup_self_check,
        "_fetch_admin_password_hash",
        AsyncMock(return_value=(None, None)),
    )

    result = await startup_self_check._check_initial_admin_password(settings)

    assert result.status == "pass"
    assert "未检测到管理员账号" in result.summary
