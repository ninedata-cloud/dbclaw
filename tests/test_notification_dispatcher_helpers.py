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
def test_is_historical_alert_true_when_older_than_max_days():
    alert = SimpleNamespace(created_at=now() - timedelta(days=4))
    assert dispatcher._is_historical_alert(alert) is True


@pytest.mark.unit
def test_is_historical_alert_false_when_within_max_days():
    alert = SimpleNamespace(created_at=now() - timedelta(days=2))
    assert dispatcher._is_historical_alert(alert) is False


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
    assert "缺少必填参数" in logs[0].error_message
    assert db.commit.await_count == 1
    assert len(added) >= 2
