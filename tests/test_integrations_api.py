from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.database import get_db
from backend.routers.auth import get_current_user
from backend.routers.integrations import router


def _integration_response_obj():
    return SimpleNamespace(
        id=1,
        integration_code="custom_hook",
        name="Hook",
        description="desc",
        integration_type="outbound_notification",
        category="webhook",
        is_builtin=False,
        code="print('ok')",
        config_schema={},
        enabled=True,
        last_run_at=None,
        last_error=None,
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        updated_at=datetime(2026, 1, 1, 0, 0, 0),
    )


def _build_client(client_factory, db_override_factory, user):
    db, db_override = db_override_factory()
    client = client_factory(
        router=router,
        overrides={
            get_current_user: lambda: user,
            get_db: db_override,
        },
    )
    return client, db


@pytest.mark.api
def test_create_integration_requires_admin(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))
    create_mock = mocker.patch("backend.services.integration_service.IntegrationService.create_integration", AsyncMock())

    response = client.post(
        "/api/integrations",
        json={
            "integration_id": "x1",
            "name": "x",
            "integration_type": "outbound_notification",
            "category": "custom",
            "is_builtin": False,
            "code": "print(1)",
            "enabled": True,
        },
    )

    assert response.status_code == 403
    create_mock.assert_not_called()


@pytest.mark.api
def test_create_integration_rejects_builtin_template_creation(client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))

    response = client.post(
        "/api/integrations",
        json={
            "integration_id": "builtin_x",
            "name": "builtin",
            "integration_type": "outbound_notification",
            "category": "custom",
            "is_builtin": True,
            "code": "print(1)",
            "enabled": True,
        },
    )

    assert response.status_code == 400
    assert "不能创建内置模板" in response.text


@pytest.mark.api
def test_delete_integration_requires_admin(client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))

    response = client.delete("/api/integrations/1")

    assert response.status_code == 403


@pytest.mark.api
def test_test_integration_maps_value_error_to_400(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch(
        "backend.services.integration_service.IntegrationService.test_integration",
        AsyncMock(side_effect=ValueError("boom")),
    )

    response = client.post("/api/integrations/1/test", json={"params": {}})

    assert response.status_code == 400
    assert "boom" in response.text


@pytest.mark.api
def test_get_integration_returns_response_payload(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch(
        "backend.services.integration_service.IntegrationService.get_integration",
        AsyncMock(return_value=_integration_response_obj()),
    )

    response = client.get("/api/integrations/1")

    assert response.status_code == 200
    assert response.json()["integration_id"] == "custom_hook"


@pytest.mark.api
def test_get_integration_returns_404_when_missing(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch(
        "backend.services.integration_service.IntegrationService.get_integration",
        AsyncMock(return_value=None),
    )

    response = client.get("/api/integrations/404")

    assert response.status_code == 404


@pytest.mark.api
def test_list_integration_passes_query_filters(mocker, client_factory, db_override_factory):
    client, db = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    list_mock = mocker.patch(
        "backend.services.integration_service.IntegrationService.list_integration",
        AsyncMock(return_value=[]),
    )

    response = client.get(
        "/api/integrations",
        params={
            "integration_type": "outbound_notification",
            "category": "webhook",
            "enabled": "true",
            "is_builtin": "false",
        },
    )

    assert response.status_code == 200
    list_mock.assert_awaited_once_with(
        db,
        integration_type="outbound_notification",
        category="webhook",
        enabled=True,
        is_builtin=False,
    )


@pytest.mark.api
def test_update_integration_returns_404_for_missing_target(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    get_mock = mocker.patch(
        "backend.services.integration_service.IntegrationService.get_integration",
        AsyncMock(return_value=None),
    )
    update_mock = mocker.patch(
        "backend.services.integration_service.IntegrationService.update_integration",
        AsyncMock(),
    )

    response = client.put("/api/integrations/99", json={"name": "updated"})

    assert response.status_code == 404
    get_mock.assert_awaited_once()
    update_mock.assert_not_awaited()


@pytest.mark.api
def test_load_builtin_templates_requires_admin(client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))

    response = client.post("/api/integrations/load-builtin")

    assert response.status_code == 403
