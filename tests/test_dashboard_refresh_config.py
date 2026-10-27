from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.routers.system_configs import router
from backend.services import config_service


KEY = config_service.DASHBOARD_REFRESH_INTERVAL_CONFIG_KEY


def build_client(client_factory, db_override_factory, user, config=None):
    db, override_db = db_override_factory()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=config))
    db.get.return_value = config
    client = client_factory(router=router, overrides={
        get_db: override_db,
        get_current_user: lambda: user,
    })
    return client, db


@pytest.mark.api
@pytest.mark.parametrize("value, expected", [
    (None, 15), ("30", 30), ("1", 1), ("86400", 86400),
    ("0", 15), ("86401", 15), ("bad", 15), ("1.5", 15),
])
def test_dashboard_settings_are_available_to_normal_users(
    client_factory, db_override_factory, normal_user, value, expected,
):
    config = None if value is None else SimpleNamespace(
        value=value, value_type="integer", is_encrypted=False,
    )
    client, db = build_client(client_factory, db_override_factory, normal_user, config)

    response = client.get("/api/system-configs/dashboard")

    assert response.status_code == 200
    assert response.json() == {"refresh_interval_seconds": expected}
    query = db.execute.await_args.args[0]
    assert KEY in query.compile().params.values()
    assert "system_config.is_active = true" in str(query)


@pytest.mark.api
def test_dashboard_settings_require_authentication(client_factory, db_override_factory):
    from backend.i18n.errors import ApiError

    def unauthenticated():
        raise ApiError(401, "auth.not_authenticated")

    _, override_db = db_override_factory()
    client = client_factory(router=router, overrides={
        get_db: override_db, get_current_user: unauthenticated,
    })
    assert client.get("/api/system-configs/dashboard").status_code == 401


@pytest.mark.api
def test_dashboard_read_access_does_not_grant_admin_access(
    client_factory, db_override_factory, normal_user,
):
    client, db = build_client(client_factory, db_override_factory, normal_user)
    assert client.get("/api/system-configs").status_code == 403
    assert client.post("/api/system-configs", json={
        "key": KEY, "value": "30", "value_type": "integer",
    }).status_code == 403
    assert client.put("/api/system-configs/1", json={"value": "30"}).status_code == 403
    db.commit.assert_not_awaited()


@pytest.mark.api
@pytest.mark.parametrize("method", ["post", "put"])
@pytest.mark.parametrize("value, value_type", [
    ("0", "integer"), ("-1", "integer"), ("86401", "integer"),
    ("1.5", "integer"), ("bad", "integer"), ("", "integer"),
    ("30", "string"), ("30", "float"),
])
def test_dashboard_interval_rejects_invalid_writes(
    client_factory, db_override_factory, admin_user, method, value, value_type,
):
    client, db = build_client(
        client_factory, db_override_factory, admin_user, SimpleNamespace(key=KEY),
    )
    path = "/api/system-configs" if method == "post" else "/api/system-configs/1"
    response = getattr(client, method)(path, json={
        "key": KEY, "value": value, "value_type": value_type,
    })
    assert response.status_code == 400
    db.commit.assert_not_awaited()


@pytest.mark.api
def test_dashboard_interval_update_is_used_by_next_read(
    client_factory, db_override_factory, admin_user,
):
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc)
    config = SimpleNamespace(
        id=1, key=KEY, value="15", value_type="integer", category="dashboard",
        description="", is_active=True, is_encrypted=False,
        created_at=timestamp, updated_at=timestamp,
    )
    client, db = build_client(client_factory, db_override_factory, admin_user, config)

    response = client.put("/api/system-configs/1", json={"value": "45"})
    assert response.status_code == 200
    assert client.get("/api/system-configs/dashboard").json() == {"refresh_interval_seconds": 45}
    db.commit.assert_awaited_once()

    # A disabled/deleted record is excluded by get_config's active filter.
    db.execute.return_value.scalar_one_or_none.return_value = None
    assert client.get("/api/system-configs/dashboard").json() == {"refresh_interval_seconds": 15}
