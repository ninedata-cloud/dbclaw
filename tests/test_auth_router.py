from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.routers.auth import router


def _build_client(current_user=None, db=None):
    app = FastAPI()
    app.include_router(router)
    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user

    async def _db_override():
        yield db or AsyncMock()

    app.dependency_overrides[get_db] = _db_override
    return TestClient(app)


@pytest.mark.api
def test_login_returns_401_for_invalid_password(mocker):
    db = AsyncMock()
    db.add = MagicMock()
    user = SimpleNamespace(id=1, username="admin", password_hash="h", is_active=True)
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user))
    mocker.patch("backend.routers.auth.verify_password", return_value=False)
    client = _build_client(db=db)
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    assert resp.status_code == 401


@pytest.mark.api
def test_login_returns_403_for_inactive_user(mocker):
    db = AsyncMock()
    db.add = MagicMock()
    user = SimpleNamespace(id=1, username="admin", password_hash="h", is_active=False)
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user))
    mocker.patch("backend.routers.auth.verify_password", return_value=True)
    client = _build_client(db=db)
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "ok"})
    assert resp.status_code == 403
    db.commit.assert_awaited_once()


@pytest.mark.api
def test_login_success_sets_cookie_and_returns_user(mocker):
    db = AsyncMock()
    db.add = MagicMock()
    user = SimpleNamespace(
        id=1,
        username="admin",
        password_hash="h",
        is_active=True,
        session_version=2,
        is_admin=True,
        email=None,
        display_name=None,
        phone=None,
    )
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user))
    mocker.patch("backend.routers.auth.verify_password", return_value=True)
    create_session = mocker.patch("backend.routers.auth.SessionService.create_session", AsyncMock(return_value="sid-1"))
    client = _build_client(db=db)
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "ok"})
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "admin"
    assert "set-cookie" in resp.headers
    assert "sid-1" in resp.headers["set-cookie"]
    create_session.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.api
def test_get_me_returns_current_user():
    user = SimpleNamespace(id=1, username="admin", is_active=True, is_admin=True)
    client = _build_client(current_user=user)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


@pytest.mark.api
def test_logout_all_increments_session_version(mocker):
    db = AsyncMock()
    user = SimpleNamespace(id=1, session_version=2)
    revoke = mocker.patch("backend.routers.auth.SessionService.revoke_user_session", AsyncMock())
    client = _build_client(current_user=user, db=db)
    resp = client.post("/api/auth/logout-all")
    assert resp.status_code == 200
    assert user.session_version == 3
    revoke.assert_awaited_once()


@pytest.mark.api
def test_logout_revokes_current_session_when_cookie_present(mocker):
    db = AsyncMock()
    user = SimpleNamespace(id=1)
    get_active = mocker.patch(
        "backend.routers.auth.SessionService.get_active_session",
        AsyncMock(return_value=SimpleNamespace(id=10)),
    )
    revoke = mocker.patch("backend.routers.auth.SessionService.revoke_session", AsyncMock())
    client = _build_client(current_user=user, db=db)
    client.cookies.set("dbclaw_session_id", "sid-1")
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out"
    get_active.assert_awaited_once()
    revoke.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.api
def test_change_password_rejects_invalid_old_password(mocker):
    user = SimpleNamespace(id=1, password_hash="x")
    mocker.patch("backend.routers.auth.verify_password", return_value=False)
    client = _build_client(current_user=user, db=AsyncMock())
    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": "bad", "new_password": "newpass123"},
    )
    assert resp.status_code == 400


@pytest.mark.api
def test_change_password_success_updates_version_and_revokes(mocker):
    db = AsyncMock()
    user = SimpleNamespace(id=1, password_hash="old", session_version=2)
    mocker.patch("backend.routers.auth.verify_password", return_value=True)
    mocker.patch("backend.routers.auth.hash_password", return_value="new-hash")
    revoke = mocker.patch("backend.routers.auth.SessionService.revoke_user_session", AsyncMock())
    client = _build_client(current_user=user, db=db)
    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": "old", "new_password": "newpass123"},
    )
    assert resp.status_code == 200
    assert user.password_hash == "new-hash"
    assert user.session_version == 3
    revoke.assert_awaited_once_with(db, 1, "password_changed")
    db.commit.assert_awaited_once()
