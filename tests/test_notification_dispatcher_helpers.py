from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import notification_dispatcher as dispatcher
from backend.utils.datetime_helper import now


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AsyncSessionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.unit
def test_coerce_float_supports_percent_strings():
    assert dispatcher._coerce_float("91.5%") == 91.5
    assert dispatcher._coerce_float("  ") is None
    assert dispatcher._coerce_float(True) is None


@pytest.mark.unit
def test_display_mappings_fallback_to_unknown():
    assert dispatcher._alert_type_display("threshold_violation") == "超过阈值"
    assert dispatcher._alert_type_display(None) == "未知"
    assert dispatcher._severity_display("critical") == "严重"
    assert dispatcher._severity_display("x") == "x"


@pytest.mark.unit
def test_get_required_integration_params_filters_invalid_values():
    integration = SimpleNamespace(config_schema={"required": ["token", "", 1, None, "room"]})
    assert dispatcher._get_required_integration_params(integration) == ["token", "room"]


@pytest.mark.unit
def test_render_notification_metric_summary_formats_native_metrics():
    summary = dispatcher._render_notification_metric_summary(
        {"cpu_percent": "88.1", "threads_running": 17},
        ["cpu_usage", "connections_active"],
    )
    assert "CPU 使用率" in (summary or "")
    assert "88.1%" in (summary or "")
    assert "活跃连接数" in (summary or "")


@pytest.mark.unit
def test_lookup_metric_value_uses_alias_and_formatter_handles_types():
    value = dispatcher._lookup_metric_value({"threads_connected": "12"}, "connections_total")
    assert value == 12.0
    assert dispatcher._format_native_metric_value("connections_total", 12.2) == "12"
    assert dispatcher._format_native_metric_value("longest_transaction_sec", 7.7) == "8 秒"


@pytest.mark.unit
def test_format_diagnosis_markdown_deduplicates_and_limits_items():
    text = "1. 扩容连接池\n2. 扩容连接池\n3. 优化慢 SQL"
    output = dispatcher._format_diagnosis_markdown(text, max_items=2)
    assert output == "- 扩容连接池\n- 优化慢 SQL"


@pytest.mark.unit
def test_should_skip_for_probe_failure_only_non_probe_alerts():
    normal_alert = SimpleNamespace(metric_name="cpu_usage")
    probe_alert = SimpleNamespace(metric_name="network_probe")

    assert dispatcher._should_skip_for_probe_failure(normal_alert, has_probe_failure=True) is True
    assert dispatcher._should_skip_for_probe_failure(probe_alert, has_probe_failure=True) is False
    assert dispatcher._should_skip_for_probe_failure(normal_alert, has_probe_failure=False) is False


@pytest.mark.unit
def test_build_active_alert_payload_for_connection_failure():
    alert = SimpleNamespace(
        id=9,
        severity="high",
        content="ignored",
        created_at=now(),
        alert_type="system_error",
        metric_name="connection_status",
        metric_value=None,
        threshold_value=None,
        trigger_reason="connection failed: timeout",
    )
    payload = dispatcher._build_active_alert_payload(
        alert,
        datasource=SimpleNamespace(name="prod"),
        diagnosis_payload={},
        alert_url=None,
        report_url=None,
    )
    assert "数据库连接失败" in payload["title"]
    assert payload["metric_name"] is None
    assert payload["trigger_reason"] == "timeout"


@pytest.mark.unit
def test_build_active_alert_payload_regular_alert_includes_diagnosis_fields():
    alert = SimpleNamespace(
        id=20,
        severity="low",
        content="cpu warning",
        created_at=now(),
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        metric_value=81.0,
        threshold_value=80.0,
        trigger_reason="CPU > 80%",
    )
    payload = dispatcher._build_active_alert_payload(
        alert,
        datasource=SimpleNamespace(name="prod"),
        diagnosis_payload={"summary": "慢查询导致", "root_cause": "索引失效", "recommended_actions": "重建索引", "status": "completed"},
        alert_url="https://a",
        report_url="https://b",
        native_metric_summary="- CPU 使用率：81.0%",
    )
    assert payload["alert_url"] == "https://a"
    assert payload["report_url"] == "https://b"
    assert payload["ai_diagnosis_summary"] == "慢查询导致"
    assert payload["native_metric_summary"] is not None


@pytest.mark.unit
def test_build_recovery_payload_uses_resolved_value_when_available():
    alert = SimpleNamespace(
        id=10,
        severity="medium",
        content="cpu back to normal",
        created_at=now() - timedelta(minutes=6),
        resolved_at=now(),
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        metric_value=87.0,
        resolved_value=42.0,
        threshold_value=80.0,
        trigger_reason="cpu high",
    )
    payload = dispatcher._build_recovery_alert_payload(alert, datasource=SimpleNamespace(name="prod"))
    assert payload["status"] == "resolved"
    assert payload["recovery_value"] == 42.0
    assert "已恢复" in payload["title"]


@pytest.mark.unit
def test_build_recovery_payload_does_not_fallback_to_trigger_value():
    alert = SimpleNamespace(
        id=11,
        severity="medium",
        content="阈值：79.62\n原因：cpu_usage=100.00 高于该实例基线窗口上界 79.62",
        created_at=now() - timedelta(minutes=6),
        resolved_at=now(),
        alert_type="baseline_deviation",
        metric_name="cpu_usage",
        metric_value=100.0,
        resolved_value=None,
        threshold_value=79.62,
        trigger_reason="cpu_usage=100.00 高于该实例基线窗口上界 79.62",
    )

    payload = dispatcher._build_recovery_alert_payload(alert, datasource=SimpleNamespace(name="prod"))

    assert payload["recovery_value"] is None
    assert payload["resolved_value"] is None
    assert "恢复后值" not in payload["content"]


@pytest.mark.service
@pytest.mark.asyncio
async def test_already_delivered_true_when_sent_log_exists():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(1))
    sent = await dispatcher._already_delivered(db, alert_id=1, subscription_id=2, cooldown_minutes=30)
    assert sent is True


@pytest.mark.service
@pytest.mark.asyncio
async def test_mark_alert_notified_sets_timestamp_and_commits():
    db = AsyncMock()
    alert = SimpleNamespace(notified_at=None)
    await dispatcher._mark_alert_notified(db, alert)
    assert alert.notified_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_is_datasource_silenced_false_when_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))

    silenced = await dispatcher._is_datasource_silenced(db, datasource_id=1)

    assert silenced is False
    db.commit.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_is_datasource_silenced_true_when_within_silence_window():
    datasource = SimpleNamespace(silence_until=now() + timedelta(minutes=10), silence_reason="维护中")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(datasource))

    silenced = await dispatcher._is_datasource_silenced(db, datasource_id=1)

    assert silenced is True
    db.commit.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_is_datasource_silenced_clears_expired_window_and_commits():
    datasource = SimpleNamespace(silence_until=now() - timedelta(minutes=1), silence_reason="维护中")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(datasource))

    silenced = await dispatcher._is_datasource_silenced(db, datasource_id=1)

    assert silenced is False
    assert datasource.silence_until is None
    assert datasource.silence_reason is None
    db.commit.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_recovery_via_integration_records_missing_required_params(mocker):
    integration = SimpleNamespace(
        id=77,
        integration_id="builtin_webhook",
        name="Webhook",
        is_enabled=True,
        config_schema={"required": ["url"]},
    )
    alert = SimpleNamespace(
        id=501,
        datasource_id=1,
        event_id=None,
        severity="high",
        created_at=now() - timedelta(minutes=5),
        resolved_at=now(),
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        metric_value=90.0,
        resolved_value=30.0,
        threshold_value=80.0,
        trigger_reason="cpu high",
        content="告警恢复",
    )
    subscription = SimpleNamespace(
        id=601,
        integration_targets=[
            {
                "integration_id": 77,
                "target_id": "t-recovery",
                "name": "target-recovery",
                "enabled": True,
                "notify_on": ["recovery"],
                "params": {},
            }
        ],
    )

    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    db.commit = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarOneOrNoneResult(
            SimpleNamespace(name="prod-db", db_type="mysql", host="127.0.0.1", port=3306, database="app")
        )
    )

    mocker.patch("backend.services.notification_dispatcher.get_alive_by_id", AsyncMock(return_value=integration))

    logs = await dispatcher._send_recovery_via_integration(db, alert, subscription)

    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].channel.endswith(":recovery")
    assert "missing required parameters" in logs[0].error_message
    assert db.commit.await_count == 1
    assert len(added) >= 2


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_recovery_via_integration_skips_deleted_datasource(mocker):
    alert = SimpleNamespace(id=19, datasource_id=9, event_id=None)
    subscription = SimpleNamespace(id=8, integration_targets=[{"integration_id": 77}])
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    integration_lookup = mocker.patch(
        "backend.services.notification_dispatcher.get_alive_by_id",
        AsyncMock(),
    )

    logs = await dispatcher._send_recovery_via_integration(db, alert, subscription)

    assert logs == []
    integration_lookup.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_via_integration_skips_deleted_datasource(mocker):
    alert = SimpleNamespace(id=20, datasource_id=9)
    subscription = SimpleNamespace(id=8, integration_targets=[{"integration_id": 77}])
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    integration_lookup = mocker.patch(
        "backend.services.notification_dispatcher.get_alive_by_id",
        AsyncMock(),
    )

    logs = await dispatcher._send_via_integration(db, alert, subscription)

    assert logs == []
    integration_lookup.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_process_pending_alerts_notifies_old_still_active_alert(mocker):
    alert = SimpleNamespace(
        id=42,
        datasource_id=1,
        event_id=None,
        metric_name="cpu_usage",
        created_at=now() - timedelta(days=10),
    )
    subscription = SimpleNamespace(id=7, integration_targets=[{"integration_id": 1}])
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(SimpleNamespace(name="prod-db")))

    mocker.patch("backend.services.notification_dispatcher.async_session", return_value=_AsyncSessionContext(db))
    mocker.patch.object(dispatcher.AggregationEngine, "_get_notification_cooldown_minutes", AsyncMock(return_value=60))
    mocker.patch.object(dispatcher.AlertService, "get_pending_notifications", AsyncMock(return_value=[alert]))
    mocker.patch.object(dispatcher.AlertService, "get_all_subscriptions", AsyncMock(return_value=[subscription]))
    mocker.patch.object(dispatcher.NotificationService, "check_subscription_match", AsyncMock(return_value=True))
    mocker.patch.object(dispatcher.AggregationEngine, "should_send_alert", AsyncMock(return_value=True))
    mocker.patch("backend.services.notification_dispatcher._has_active_network_probe_failure", AsyncMock(return_value=False))
    mocker.patch("backend.services.notification_dispatcher._is_datasource_silenced", AsyncMock(return_value=False))
    mocker.patch("backend.services.notification_dispatcher._already_delivered", AsyncMock(return_value=False))
    send_mock = mocker.patch(
        "backend.services.notification_dispatcher._send_via_integration",
        AsyncMock(return_value=[SimpleNamespace(status="sent")]),
    )
    mark_mock = mocker.patch("backend.services.notification_dispatcher._mark_alert_notified", AsyncMock())
    mocker.patch("backend.services.notification_dispatcher._process_recovery_notifications", AsyncMock())

    await dispatcher._process_pending_alerts()

    send_mock.assert_awaited_once_with(db, alert, subscription, {
        "root_cause": None,
        "recommended_actions": None,
        "summary": None,
        "status": None,
    })
    mark_mock.assert_awaited_once_with(db, alert)


@pytest.mark.service
@pytest.mark.asyncio
async def test_process_pending_alerts_skips_deleted_datasource(mocker):
    alert = SimpleNamespace(
        id=44,
        datasource_id=9,
        event_id=None,
        metric_name="cpu_usage",
    )
    subscription = SimpleNamespace(id=7, integration_targets=[{"integration_id": 1}])
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))

    mocker.patch("backend.services.notification_dispatcher.async_session", return_value=_AsyncSessionContext(db))
    mocker.patch.object(dispatcher.AggregationEngine, "_get_notification_cooldown_minutes", AsyncMock(return_value=60))
    mocker.patch.object(dispatcher.AlertService, "get_pending_notifications", AsyncMock(return_value=[alert]))
    mocker.patch.object(dispatcher.AlertService, "get_all_subscriptions", AsyncMock(return_value=[subscription]))
    mocker.patch("backend.services.notification_dispatcher._has_active_network_probe_failure", AsyncMock(return_value=False))
    mocker.patch("backend.services.notification_dispatcher._is_datasource_silenced", AsyncMock(return_value=False))
    send_mock = mocker.patch("backend.services.notification_dispatcher._send_via_integration", AsyncMock())
    mocker.patch("backend.services.notification_dispatcher._process_recovery_notifications", AsyncMock())

    await dispatcher._process_pending_alerts()

    send_mock.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_process_recovery_notifications_notifies_old_alert_resolved_recently(mocker):
    alert = SimpleNamespace(
        id=43,
        datasource_id=1,
        metric_name="cpu_usage",
        created_at=now() - timedelta(days=10),
        resolved_at=now(),
    )
    subscription = SimpleNamespace(id=8)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(SimpleNamespace(id=1)))

    mocker.patch.object(dispatcher.AlertService, "get_pending_recovery_notifications", AsyncMock(return_value=[alert]))
    mocker.patch.object(dispatcher.AlertService, "get_all_subscriptions", AsyncMock(return_value=[subscription]))
    mocker.patch.object(dispatcher.AlertService, "has_alert_notification_for_subscription", AsyncMock(return_value=True))
    mocker.patch.object(dispatcher.AlertService, "has_recovery_notification_for_subscription", AsyncMock(return_value=False))
    mocker.patch.object(dispatcher.NotificationService, "check_subscription_match", AsyncMock(return_value=True))
    mocker.patch("backend.services.notification_dispatcher._has_active_network_probe_failure", AsyncMock(return_value=False))
    mocker.patch("backend.services.notification_dispatcher._is_datasource_silenced", AsyncMock(return_value=False))
    send_mock = mocker.patch(
        "backend.services.notification_dispatcher._send_recovery_via_integration",
        AsyncMock(return_value=[SimpleNamespace(status="sent")]),
    )

    await dispatcher._process_recovery_notifications(db)

    send_mock.assert_awaited_once_with(db, alert, subscription)


@pytest.mark.service
@pytest.mark.asyncio
async def test_process_recovery_notifications_skips_deleted_datasource(mocker):
    alert = SimpleNamespace(
        id=45,
        datasource_id=9,
        metric_name="cpu_usage",
        created_at=now() - timedelta(days=10),
        resolved_at=now(),
    )
    subscription = SimpleNamespace(id=8)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))

    mocker.patch.object(dispatcher.AlertService, "get_pending_recovery_notifications", AsyncMock(return_value=[alert]))
    mocker.patch.object(dispatcher.AlertService, "get_all_subscriptions", AsyncMock(return_value=[subscription]))
    mocker.patch.object(dispatcher.NotificationService, "check_subscription_match", AsyncMock(return_value=True))
    mocker.patch("backend.services.notification_dispatcher._has_active_network_probe_failure", AsyncMock(return_value=False))
    mocker.patch("backend.services.notification_dispatcher._is_datasource_silenced", AsyncMock(return_value=False))
    send_mock = mocker.patch("backend.services.notification_dispatcher._send_recovery_via_integration", AsyncMock())

    await dispatcher._process_recovery_notifications(db)

    send_mock.assert_not_awaited()
