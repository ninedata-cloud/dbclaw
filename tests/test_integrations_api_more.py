from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.routers.auth import get_current_user
from backend.routers.integrations import router


def _build_client(user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user

    async def _db_override():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _db_override
    return TestClient(app)


@pytest.mark.api
def test_get_integration_returns_404_when_missing(mocker):
    client = _build_client(SimpleNamespace(is_admin=True))
    mocker.patch(
        "backend.services.integration_service.IntegrationService.get_integration",
        AsyncMock(return_value=None),
    )
    response = client.get("/api/integrations/404")
    assert response.status_code == 404


@pytest.mark.api
def test_update_integration_blocks_non_admin_for_builtin(mocker):
    client = _build_client(SimpleNamespace(is_admin=False))
    mocker.patch(
        "backend.services.integration_service.IntegrationService.get_integration",
        AsyncMock(return_value=SimpleNamespace(is_builtin=True)),
    )
    response = client.put("/api/integrations/1", json={"name": "new"})
    assert response.status_code == 403


@pytest.mark.api
def test_update_integration_returns_404_when_missing(mocker):
    client = _build_client(SimpleNamespace(is_admin=True))
    mocker.patch(
        "backend.services.integration_service.IntegrationService.get_integration",
        AsyncMock(return_value=None),
    )
    response = client.put("/api/integrations/99", json={"name": "new"})
    assert response.status_code == 404


@pytest.mark.api
def test_load_builtin_requires_admin():
    client = _build_client(SimpleNamespace(is_admin=False))
    response = client.post("/api/integrations/load-builtin")
    assert response.status_code == 403
