from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.models.alert_event  # noqa: F401
import backend.models.alert_message  # noqa: F401
import backend.models.alert_subscription  # noqa: F401
import backend.models.alert_template  # noqa: F401
import backend.models.datasource  # noqa: F401
import backend.models.inspection_config  # noqa: F401
import backend.models.integration  # noqa: F401
import backend.models.user  # noqa: F401
from backend.database import Base
from backend.models.datasource import Datasource
from backend.models.integration import Integration
from backend.models.user import User
from backend.services.alert_skill_service import execute_manage_alert_settings


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _seed_user(db_session, username: str, *, is_admin: bool = False) -> User:
    user = User(
        username=username,
        password_hash="hashed",
        is_admin=is_admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_datasource(db_session, name: str) -> Datasource:
    datasource = Datasource(
        name=name,
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        username="root",
        database=name,
        is_active=True,
    )
    db_session.add(datasource)
    await db_session.commit()
    await db_session.refresh(datasource)
    return datasource


async def _seed_integration(db_session, name: str) -> Integration:
    integration = Integration(
        integration_id=f"custom_{name}",
        name=name,
        description=f"{name} integration",
        integration_type="outbound_notification",
        category="webhook",
        code="async def execute(context, params):\n    return {'success': True}",
        config_schema={
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "title": "Webhook URL"},
            },
            "required": ["webhook_url"],
        },
        enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()
    await db_session.refresh(integration)
    return integration


@pytest.mark.asyncio
async def test_manage_alert_settings_subscription_crud_and_test(db_session):
    user = await _seed_user(db_session, "operator")
    datasource = await _seed_datasource(db_session, "orders")
    integration = await _seed_integration(db_session, "ops-webhook")

    create_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "subscription",
            "action": "create",
            "datasource_ids": [datasource.id],
            "severity_levels": ["high"],
            "integration_targets": [
                {
                    "target_id": "target_1",
                    "integration_id": integration.id,
                    "name": "Ops Webhook",
                    "enabled": True,
                    "notify_on": ["alert", "recovery"],
                    "params": {"webhook_url": "https://example.com/hook"},
                }
            ],
            "enabled": True,
        },
    )

    assert create_result["success"] is True
    subscription_id = create_result["subscription"]["id"]
    assert create_result["subscription"]["user_id"] == user.id

    list_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {"target": "subscription", "action": "list"},
    )
    assert list_result["success"] is True
    assert list_result["count"] == 1

    update_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "subscription",
            "action": "update",
            "subscription_id": subscription_id,
            "enabled": False,
            "severity_levels": ["critical"],
        },
    )
    assert update_result["success"] is True
    assert update_result["subscription"]["enabled"] is False
    assert update_result["subscription"]["severity_levels"] == ["critical"]

    get_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "subscription",
            "action": "get",
            "subscription_id": subscription_id,
        },
    )
    assert get_result["success"] is True
    assert get_result["subscription"]["id"] == subscription_id

    fake_logs = [SimpleNamespace(channel="webhook", recipient="ops", status="sent", error_message=None)]
    with patch(
        "backend.services.notification_service.NotificationService.send_notifications",
        new=AsyncMock(return_value=fake_logs),
    ):
        test_result = await execute_manage_alert_settings(
            db_session,
            user.id,
            {
                "target": "subscription",
                "action": "test",
                "subscription_id": subscription_id,
            },
        )

    assert test_result["success"] is True
    assert test_result["count"] == 1
    assert test_result["deliveries"][0]["status"] == "sent"

    delete_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "subscription",
            "action": "delete",
            "subscription_id": subscription_id,
        },
    )
    assert delete_result["success"] is True

    list_after_delete = await execute_manage_alert_settings(
        db_session,
        user.id,
        {"target": "subscription", "action": "list"},
    )
    assert list_after_delete["success"] is True
    assert list_after_delete["count"] == 0


@pytest.mark.asyncio
async def test_manage_alert_settings_template_datasource_config_and_silence(db_session):
    admin = await _seed_user(db_session, "admin_user", is_admin=True)
    user = await _seed_user(db_session, "readonly_user")
    datasource = await _seed_datasource(db_session, "billing")

    denied_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "template",
            "action": "create",
            "name": "非管理员模板",
            "template_config": {
                "alert_engine_mode": "threshold",
                "threshold_rules": {"cpu_usage": {"threshold": 80, "duration": 300}},
            },
        },
    )
    assert denied_result["success"] is False
    assert "admin" in denied_result["error"]

    create_template = await execute_manage_alert_settings(
        db_session,
        admin.id,
        {
            "target": "template",
            "action": "create",
            "name": "高 CPU 模板",
            "description": "只用于测试",
            "template_config": {
                "alert_engine_mode": "threshold",
                "threshold_rules": {"cpu_usage": {"threshold": 70, "duration": 120}},
                "baseline_config": {"enabled": False},
                "event_ai_config": {"enabled": True},
            },
        },
    )
    assert create_template["success"] is True
    template_id = create_template["template"]["id"]

    toggle_template = await execute_manage_alert_settings(
        db_session,
        admin.id,
        {
            "target": "template",
            "action": "toggle",
            "template_id": template_id,
            "enabled": False,
        },
    )
    assert toggle_template["success"] is True
    assert toggle_template["template"]["enabled"] is False

    reenable_template = await execute_manage_alert_settings(
        db_session,
        admin.id,
        {
            "target": "template",
            "action": "toggle",
            "template_id": template_id,
            "enabled": True,
        },
    )
    assert reenable_template["success"] is True
    assert reenable_template["template"]["enabled"] is True

    default_template = await execute_manage_alert_settings(
        db_session,
        admin.id,
        {
            "target": "template",
            "action": "set_default",
            "template_id": template_id,
        },
    )
    assert default_template["success"] is True
    assert default_template["template"]["is_default"] is True

    config_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "datasource_config",
            "action": "update",
            "datasource_id": datasource.id,
            "enabled": True,
            "schedule_interval": 3600,
            "use_ai_analysis": False,
            "alert_template_id": template_id,
            "threshold_rules": {"cpu_usage": {"threshold": 999, "duration": 5}},
        },
    )
    assert config_result["success"] is True
    assert config_result["config"]["enabled"] is True
    assert config_result["config"]["schedule_interval"] == 3600
    assert config_result["config"]["use_ai_analysis"] is False
    assert config_result["config"]["alert_template_id"] == template_id
    assert config_result["config"]["threshold_rules"]["cpu_usage"]["threshold"] == 70

    silence_result = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "silence",
            "action": "set",
            "datasource_id": datasource.id,
            "hours": 1.5,
            "reason": "发布窗口",
        },
    )
    assert silence_result["success"] is True
    assert silence_result["silence"]["is_silenced"] is True
    assert silence_result["silence"]["remaining_hours"] == 1.5

    get_silence = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "silence",
            "action": "get",
            "datasource_id": datasource.id,
        },
    )
    assert get_silence["success"] is True
    assert get_silence["silence"]["is_silenced"] is True
    assert get_silence["silence"]["silence_reason"] == "发布窗口"

    cancel_silence = await execute_manage_alert_settings(
        db_session,
        user.id,
        {
            "target": "silence",
            "action": "cancel",
            "datasource_id": datasource.id,
        },
    )
    assert cancel_silence["success"] is True
    assert cancel_silence["silence"]["is_silenced"] is False


@pytest.mark.asyncio
async def test_manage_alert_settings_admin_can_target_other_user_subscription(db_session):
    admin = await _seed_user(db_session, "boss", is_admin=True)
    target_user = await _seed_user(db_session, "teammate")
    datasource = await _seed_datasource(db_session, "inventory")
    integration = await _seed_integration(db_session, "team-webhook")

    create_result = await execute_manage_alert_settings(
        db_session,
        admin.id,
        {
            "target": "subscription",
            "action": "create",
            "user_id": target_user.id,
            "datasource_ids": [datasource.id],
            "integration_targets": [
                {
                    "target_id": "target_2",
                    "integration_id": integration.id,
                    "name": "Team Webhook",
                    "enabled": True,
                    "notify_on": ["alert"],
                    "params": {"webhook_url": "https://example.com/team"},
                }
            ],
        },
    )

    assert create_result["success"] is True
    assert create_result["subscription"]["user_id"] == target_user.id

    list_result = await execute_manage_alert_settings(
        db_session,
        admin.id,
        {
            "target": "subscription",
            "action": "list",
            "user_id": target_user.id,
        },
    )
    assert list_result["success"] is True
    assert list_result["count"] == 1
