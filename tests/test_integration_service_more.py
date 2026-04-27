from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.schemas.integration import IntegrationUpdate
from backend.services.integration_service import IntegrationService


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.unit
def test_encrypt_sensitive_params_encrypts_prefixed_values(mocker):
    encrypt = mocker.patch("backend.services.integration_service.encrypt_value", return_value="cipher")
    result = IntegrationService.encrypt_sensitive_params(
        {"token": "ENCRYPT:secret", "name": "plain"}
    )
    assert result["token"] == "encrypted:cipher"
    assert result["name"] == "plain"
    encrypt.assert_called_once_with("secret")


@pytest.mark.service
@pytest.mark.asyncio
async def test_test_integration_rejects_disabled_integration(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(is_enabled=False)
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    with pytest.raises(ValueError, match="已禁用"):
        await IntegrationService.test_integration(db, 1, {})


@pytest.mark.service
@pytest.mark.asyncio
async def test_test_integration_outbound_uses_default_payload(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(is_enabled=True, integration_type="outbound_notification", code="print('ok')")
    executor = SimpleNamespace(execute_notification=AsyncMock(return_value={"success": True}))
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    mocker.patch("backend.services.integration_service.IntegrationExecutor", return_value=executor)

    result = await IntegrationService.test_integration(db, 1, {"a": 1})

    assert result["success"] is True
    executor.execute_notification.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_list_integration_returns_scalars_all():
    rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows)))
    result = await IntegrationService.list_integration(db, enabled=True)
    assert len(result) == 2


@pytest.mark.service
@pytest.mark.asyncio
async def test_create_integration_raises_when_code_exists():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(SimpleNamespace(id=1)))
    data = SimpleNamespace(
        integration_code="dup",
        name="x",
        description=None,
        integration_type="outbound_notification",
        category="webhook",
        is_builtin=False,
        code="print(1)",
        config_schema={},
        enabled=True,
    )
    with pytest.raises(ValueError, match="已存在"):
        await IntegrationService.create_integration(db, data)


@pytest.mark.service
@pytest.mark.asyncio
async def test_create_integration_adds_and_refreshes_new_integration():
    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    db.execute = AsyncMock(return_value=_Result(None))
    data = SimpleNamespace(
        integration_code="custom_webhook",
        name="Custom Webhook",
        description="desc",
        integration_type="outbound_notification",
        category="webhook",
        is_builtin=False,
        code="print(1)",
        config_schema={"type": "object"},
        enabled=True,
    )

    created = await IntegrationService.create_integration(db, data)

    assert created.integration_code == "custom_webhook"
    assert created.is_enabled is True
    assert added == [created]
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(created)


@pytest.mark.service
@pytest.mark.asyncio
async def test_update_custom_integration_updates_all_editable_fields(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(
        id=22,
        integration_id="custom_hook",
        is_builtin=False,
        name="old",
        description="old",
        code="old",
        config_schema={},
        is_enabled=True,
        updated_at=None,
    )
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    data = IntegrationUpdate(
        name="new",
        description="new-desc",
        code="print('new')",
        config_schema={"required": ["url"]},
        enabled=False,
    )

    updated = await IntegrationService.update_integration(db, 22, data)

    assert updated.name == "new"
    assert updated.description == "new-desc"
    assert updated.code == "print('new')"
    assert updated.config_schema == {"required": ["url"]}
    assert updated.is_enabled is False
    assert updated.updated_at is not None
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(integration)


@pytest.mark.service
@pytest.mark.asyncio
async def test_update_integration_raises_when_missing(mocker):
    db = AsyncMock()
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=None))

    with pytest.raises(ValueError, match="Integration 不存在"):
        await IntegrationService.update_integration(db, 404, IntegrationUpdate(name="x"))


@pytest.mark.service
@pytest.mark.asyncio
async def test_delete_custom_integration_soft_deletes_and_commits(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(is_builtin=False, name="custom", soft_delete=mocker.Mock())
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))

    await IntegrationService.delete_integration(db, 5)

    integration.soft_delete.assert_called_once_with(None)
    db.commit.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_test_integration_inbound_returns_message_when_datasource_missing(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(is_enabled=True, integration_type="inbound_metric")
    mocker.patch(
        "backend.services.integration_service.get_alive_by_id",
        AsyncMock(side_effect=[integration, None]),
    )

    result = await IntegrationService.test_integration(db, 1, {}, datasource_id=99)

    assert result["success"] is False
    assert "数据源 ID 99 不存在" in result["message"]


@pytest.mark.service
@pytest.mark.asyncio
async def test_test_integration_inbound_collects_metrics_with_first_datasource(mocker):
    db = AsyncMock()
    integration = SimpleNamespace(is_enabled=True, integration_type="inbound_metric", code="print('collect')")
    datasource = SimpleNamespace(id=1, name="prod", db_type="mysql", external_instance_id="rm-1")
    db.execute = AsyncMock(return_value=_Result(datasource))
    mocker.patch("backend.services.integration_service.get_alive_by_id", AsyncMock(return_value=integration))
    executor = SimpleNamespace(
        execute_metric_collection=AsyncMock(return_value=[{"name": "cpu_usage", "value": 80}])
    )
    mocker.patch("backend.services.integration_service.IntegrationExecutor", return_value=executor)

    result = await IntegrationService.test_integration(db, 1, {"token": "x"})

    assert result["success"] is True
    assert result["data"]["metrics"] == [{"name": "cpu_usage", "value": 80}]
    executor.execute_metric_collection.assert_awaited_once()
