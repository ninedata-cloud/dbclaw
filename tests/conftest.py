import sys
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def admin_user():
    return SimpleNamespace(id=1, username="admin", is_admin=True)


@pytest.fixture
def normal_user():
    return SimpleNamespace(id=2, username="user", is_admin=False)


@pytest.fixture
def fake_async_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.add = AsyncMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def simple_app() -> FastAPI:
    return FastAPI()


@pytest.fixture
def test_client(simple_app: FastAPI) -> TestClient:
    return TestClient(simple_app)


def override_async_dependency(value):
    async def _dependency() -> AsyncIterator[object]:
        yield value

    return _dependency


@pytest.fixture
def app_factory():
    def _build(router=None, overrides=None) -> FastAPI:
        app = FastAPI()
        if router is not None:
            app.include_router(router)
        for dependency, provider in (overrides or {}).items():
            app.dependency_overrides[dependency] = provider
        return app

    return _build


@pytest.fixture
def client_factory(app_factory):
    def _build(router=None, overrides=None) -> TestClient:
        app = app_factory(router=router, overrides=overrides)
        return TestClient(app)

    return _build


@pytest.fixture
def db_override_factory():
    def _build(db=None):
        database = db or AsyncMock()

        async def _db_override() -> AsyncIterator[object]:
            yield database

        return database, _db_override

    return _build
