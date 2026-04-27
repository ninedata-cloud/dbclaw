from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import notification_dispatcher as dispatcher


@pytest.mark.unit
def test_render_notification_metric_summary_formats_values():
    raw = {"cpu_percent": "80.5%", "threads_running": 12}

    summary = dispatcher._render_notification_metric_summary(raw, ["cpu_usage", "connections_active"])

    assert "CPU 使用率：80.5%" in summary
    assert "活跃连接数：12" in summary


@pytest.mark.unit
def test_build_active_alert_payload_connection_failure_branch(mocker):
    mocker.patch("backend.services.notification_dispatcher.is_connection_status_alert", return_value=True)
    mocker.patch("backend.services.notification_dispatcher.extract_connection_failure_detail", return_value="timeout")
    alert = SimpleNamespace(
        id=1,
        severity="high",
        content="连接失败",
        alert_type="system_error",
        metric_name="connection_status",
        metric_value=0,
        threshold_value=1,
        trigger_reason="timeout",
        created_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    datasource = SimpleNamespace(name="prod-db")

    payload = dispatcher._build_active_alert_payload(
        alert,
        datasource,
        {"summary": None, "root_cause": None, "recommended_actions": None, "status": None},
        None,
        None,
    )

    assert payload["alert_type"] == "连接失败"
    assert payload["metric_name"] is None
    assert "数据库连接失败" in payload["title"]


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_via_integration_records_missing_required_params(mocker):
    integration = SimpleNamespace(
        id=99,
        integration_id="builtin_webhook",
        name="Webhook",
        is_enabled=True,
        config_schema={"required": ["url"]},
    )
    alert = SimpleNamespace(
        id=1001,
        datasource_id=1,
        event_id=None,
        severity="high",
        created_at=datetime(2026, 1, 1, 9, 0, 0),
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        metric_value=90.0,
        threshold_value=80.0,
        trigger_reason="cpu high",
        content="告警内容",
    )
    subscription = SimpleNamespace(
        id=2001,
        integration_targets=[
            {
                "integration_id": 99,
                "target_id": "t1",
                "name": "target-webhook",
                "enabled": True,
                "notify_on": ["alert"],
                "params": {},
            }
        ],
    )

    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    db.commit = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(
            scalar_one_or_none=lambda: SimpleNamespace(name="prod-db", db_type="mysql", host="127.0.0.1", port=3306)
        )
    )

    mocker.patch("backend.services.notification_dispatcher.get_alive_by_id", AsyncMock(return_value=integration))
    mocker.patch("backend.services.notification_dispatcher._build_ai_native_metric_summary", AsyncMock(return_value=None))
    mocker.patch("backend.services.alert_service.normalize_alert_diagnosis_fields", return_value={"summary": None, "root_cause": None, "recommended_actions": None})
    mocker.patch("backend.services.public_share_service.PublicShareService.get_external_base_url", AsyncMock(return_value=None))

    logs = await dispatcher._send_via_integration(db, alert, subscription)

    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert "缺少必填参数" in logs[0].error_message
    assert db.commit.await_count == 1
    assert len(added) >= 2


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_via_integration_skips_invalid_or_disabled_targets(mocker):
    alert = SimpleNamespace(
        id=1002,
        datasource_id=1,
        event_id=None,
        severity="medium",
        created_at=datetime(2026, 1, 1, 9, 0, 0),
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        metric_value=75.0,
        threshold_value=70.0,
        trigger_reason="cpu warning",
        content="告警内容",
    )
    subscription = SimpleNamespace(
        id=2002,
        integration_targets=[
            "not-a-dict",
            {"integration_id": 1, "target_id": "disabled", "enabled": False},
            {"integration_id": 2, "target_id": "recovery-only", "notify_on": ["recovery"]},
            {"target_id": "missing-integration"},
        ],
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(
            scalar_one_or_none=lambda: SimpleNamespace(name="prod-db", db_type="mysql", host="127.0.0.1", port=3306)
        )
    )
    get_integration = mocker.patch("backend.services.notification_dispatcher.get_alive_by_id", AsyncMock())
    executor_cls = mocker.patch("backend.services.integration_executor.IntegrationExecutor")
    mocker.patch("backend.services.public_share_service.PublicShareService.get_external_base_url", AsyncMock(return_value=None))

    logs = await dispatcher._send_via_integration(db, alert, subscription)

    assert logs == []
    get_integration.assert_not_awaited()
    executor_cls.assert_not_called()
    db.commit.assert_not_awaited()
