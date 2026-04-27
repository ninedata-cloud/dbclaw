from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.routers.alerts import router
from backend.schemas.alert import AlertMessageResponse


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


def _alert_response(alert_id: int = 1) -> AlertMessageResponse:
    return AlertMessageResponse(
        id=alert_id,
        datasource_id=1,
        alert_type="threshold_violation",
        severity="high",
        title="CPU告警",
        content="CPU > 80%",
        metric_name="cpu_usage",
        metric_value=92.0,
        threshold_value=80.0,
        trigger_reason="持续高负载",
        status="active",
        acknowledged_by=None,
        acknowledged_at=None,
        resolved_at=None,
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        updated_at=datetime(2026, 1, 1, 0, 0, 0),
    )


def _subscription_response(subscription_id: int = 1, user_id: int = 2):
    ts = datetime(2026, 1, 1, 0, 0, 0)
    return SimpleNamespace(
        id=subscription_id,
        user_id=user_id,
        datasource_ids=[1],
        severity_levels=["high"],
        time_ranges=[],
        integration_targets=[
            {
                "target_id": "bot-1",
                "integration_id": 10,
                "name": "默认机器人",
                "enabled": True,
                "notify_on": ["alert", "recovery"],
                "params": {},
            }
        ],
        enabled=True,
        aggregation_script=None,
        created_at=ts,
        updated_at=ts,
    )


@pytest.mark.api
def test_acknowledge_alert_returns_404_when_missing(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))
    mocker.patch("backend.routers.alerts.AlertService.acknowledge_alert", AsyncMock(return_value=None))

    response = client.post("/api/alerts/100/acknowledge", json={})

    assert response.status_code == 404


@pytest.mark.api
def test_acknowledge_alert_success(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))
    mocker.patch("backend.routers.alerts.AlertService.acknowledge_alert", AsyncMock(return_value=SimpleNamespace(id=1)))
    mocker.patch("backend.routers.alerts._build_alert_response", AsyncMock(return_value=_alert_response(1)))

    response = client.post("/api/alerts/1/acknowledge", json={})

    assert response.status_code == 200
    assert response.json()["id"] == 1


@pytest.mark.api
def test_resolve_alert_success(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch("backend.routers.alerts.AlertService.resolve_alert", AsyncMock(return_value=SimpleNamespace(id=5)))
    mocker.patch("backend.routers.alerts._build_alert_response", AsyncMock(return_value=_alert_response(5)))

    response = client.post("/api/alerts/5/resolve")

    assert response.status_code == 200
    assert response.json()["id"] == 5


@pytest.mark.api
def test_subscription_list_blocks_cross_user_for_non_admin(client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))

    response = client.get("/api/alerts/subscriptions/list", params={"user_id": 9})

    assert response.status_code == 403
    assert "不能访问其他用户的订阅" in response.text


@pytest.mark.api
def test_subscription_list_allows_admin_cross_user(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch("backend.routers.alerts.AlertService.get_user_subscriptions", AsyncMock(return_value=[]))

    response = client.get("/api/alerts/subscriptions/list", params={"user_id": 9})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.api
def test_resolve_alert_returns_404_when_missing(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch("backend.routers.alerts.AlertService.resolve_alert", AsyncMock(return_value=None))

    response = client.post("/api/alerts/404/resolve")

    assert response.status_code == 404


@pytest.mark.api
def test_create_subscription_rejects_cross_user_for_non_admin(client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))

    response = client.post(
        "/api/alerts/subscriptions",
        json={
            "user_id": 9,
            "datasource_ids": [1],
            "severity_levels": ["high"],
            "integration_targets": [
                {
                    "target_id": "bot-1",
                    "integration_id": 10,
                    "name": "告警机器人",
                }
            ],
        },
    )

    assert response.status_code == 403


@pytest.mark.api
def test_create_subscription_validates_required_targets(client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))

    response = client.post(
        "/api/alerts/subscriptions",
        json={
            "datasource_ids": [1],
            "severity_levels": ["high"],
            "integration_targets": [],
        },
    )

    assert response.status_code == 422


@pytest.mark.api
def test_update_subscription_returns_404_when_not_found(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=1, is_admin=True))
    mocker.patch("backend.routers.alerts._get_subscription_for_user", AsyncMock(return_value=_subscription_response()))
    mocker.patch("backend.routers.alerts.AlertService.update_subscription", AsyncMock(return_value=None))

    response = client.put("/api/alerts/subscriptions/10", json={"enabled": False})

    assert response.status_code == 404


@pytest.mark.api
def test_delete_subscription_returns_404_when_not_found(mocker, client_factory, db_override_factory):
    client, _ = _build_client(client_factory, db_override_factory, SimpleNamespace(id=2, is_admin=False))
    mocker.patch("backend.routers.alerts.AlertService.delete_subscription", AsyncMock(return_value=False))

    response = client.delete("/api/alerts/subscriptions/99")

    assert response.status_code == 404
