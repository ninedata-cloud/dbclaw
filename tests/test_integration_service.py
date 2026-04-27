from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.schemas.integration import IntegrationUpdate
from backend.services.integration_service import IntegrationService


@pytest.mark.unit
def test_encrypt_sensitive_params_only_encrypts_prefixed_values(mocker):
    mocker.patch("backend.services.integration_service.encrypt_value", return_value="cipher")

    result = IntegrationService.encrypt_sensitive_params(
        {"token": "ENCRYPT:abc", "plain": "ok", "num": 1}
    )

    assert result["token"] == "encrypted:cipher"
    assert result["plain"] == "ok"
    assert result["num"] == 1


@pytest.mark.service
@pytest.mark.asyncio
async def test_update_builtin_non_bot_only_allows_enabled_change(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(
        id=10,
        integration_id="builtin_webhook",
        is_builtin=True,
        name="old",
        description="old-desc",
        code="old-code",
        config_schema={"type": "object"},
        is_enabled=True,
        updated_at=None,
    )
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    data = IntegrationUpdate(name="new-name", enabled=False)

    updated = await IntegrationService.update_integration(db, 10, data)

    assert updated.is_enabled is False
    assert updated.name == "old"
    assert isinstance(updated.updated_at, datetime)


@pytest.mark.service
@pytest.mark.asyncio
async def test_delete_builtin_raises_error(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(is_builtin=True)
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))

    with pytest.raises(ValueError, match="不能删除内置模板"):
        await IntegrationService.delete_integration(db, 1)


@pytest.mark.service
@pytest.mark.asyncio
async def test_test_integration_outbound_uses_default_payload(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(id=11, is_enabled=True, integration_type="outbound_notification", code="print('x')")
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    mocker.patch.object(IntegrationService, "encrypt_sensitive_params", return_value={"url": "x"})

    executor_instance = SimpleNamespace(
        execute_notification=AsyncMock(return_value={"success": True, "message": "ok"})
    )
    executor_cls = mocker.patch("backend.services.integration_service.IntegrationExecutor", return_value=executor_instance)

    result = await IntegrationService.test_integration(db, 11, {"url": "x"})

    assert result["success"] is True
    assert executor_cls.called
    assert executor_instance.execute_notification.await_count == 1


@pytest.mark.service
@pytest.mark.asyncio
async def test_test_integration_unsupported_type_returns_failure(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(id=12, is_enabled=True, integration_type="unknown_type")
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    mocker.patch.object(IntegrationService, "encrypt_sensitive_params", return_value={})

    result = await IntegrationService.test_integration(db, 12, {})

    assert result["success"] is False
    assert "不支持的 Integration 类型" in result["message"]
