from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.notification_service import NotificationService


class _ConfigResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


def _alert():
    return SimpleNamespace(
        id=1,
        datasource_id=1,
        severity="high",
        alert_type="threshold_violation",
        title="CPU 高",
        content="CPU > 80%",
        metric_name="cpu_usage",
        metric_value=91.2,
        threshold_value=80.0,
        trigger_reason="持续高负载",
        created_at=datetime(2026, 1, 1, 8, 0, 0),
    )


@pytest.mark.unit
def test_format_diagnosis_markdown_deduplicates_and_limits_items():
    text = "1. 慢查询增多\n2. 慢查询增多\n3. 检查索引\n4. 调整参数"

    result = NotificationService._format_diagnosis_markdown(text, max_items=2)

    assert result == "- 慢查询增多\n- 检查索引"


@pytest.mark.unit
def test_format_diagnosis_markdown_single_item_returns_plain_text():
    result = NotificationService._format_diagnosis_markdown(" 1. 仅一条结论 ")
    assert result == "仅一条结论"


@pytest.mark.unit
def test_format_diagnosis_markdown_empty_input_returns_none():
    assert NotificationService._format_diagnosis_markdown(" \n ; ; ") is None


@pytest.mark.unit
def test_build_feishu_payload_includes_ai_sections():
    alert = SimpleNamespace(
        severity="high",
        alert_type="threshold_violation",
        title="CPU 高",
        metric_name="cpu_usage",
        metric_value=91.2,
        threshold_value=80.0,
        trigger_reason="持续高负载",
        created_at=datetime(2026, 1, 1, 8, 0, 0),
        root_cause="1. 索引失效",
        recommended_actions="1. 重建索引",
        ai_diagnosis_summary="慢查询集中在订单表",
    )
    datasource = SimpleNamespace(name="prod-db", db_type="mysql", host="127.0.0.1", port=3306, database="app")

    payload = NotificationService._build_feishu_payload(alert, datasource)
    elements = payload["card"]["elements"]
    rendered = "\n".join(str(item) for item in elements)

    assert payload["msg_type"] == "interactive"
    assert "AI 诊断" in rendered
    assert "根本原因" in rendered
    assert "处置建议" in rendered


@pytest.mark.unit
def test_build_feishu_payload_uses_summary_when_root_cause_missing():
    alert = SimpleNamespace(
        severity="medium",
        alert_type="threshold_violation",
        title="连接数高",
        metric_name="connections",
        metric_value=120.0,
        threshold_value=100.0,
        trigger_reason="连接突增",
        created_at=datetime(2026, 1, 1, 8, 0, 0),
        root_cause="",
        recommended_actions="",
        ai_diagnosis_summary="1. 新上线批任务导致连接数上升",
    )
    payload = NotificationService._build_feishu_payload(alert, None)
    rendered = "\n".join(str(item) for item in payload["card"]["elements"])
    assert "AI 诊断" in rendered
    assert "诊断摘要" in rendered
    assert "根本原因" not in rendered


@pytest.mark.unit
def test_build_dingtalk_url_adds_sign_when_secret(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1000.0)
    url = NotificationService._build_dingtalk_url(
        "https://oapi.dingtalk.com/robot/send?access_token=abc",
        "secret-token",
    )

    assert "timestamp=" in url
    assert "sign=" in url


@pytest.mark.unit
def test_build_dingtalk_url_without_secret_returns_original():
    src = "https://oapi.dingtalk.com/robot/send?access_token=abc"
    assert NotificationService._build_dingtalk_url(src, None) == src


@pytest.mark.service
@pytest.mark.asyncio
async def test_check_subscription_match_returns_false_when_datasource_not_in_filter():
    alert = SimpleNamespace(datasource_id=2, severity="high")
    subscription = SimpleNamespace(
        datasource_ids=[1],
        severity_levels=[],
        time_ranges=[],
    )
    matched = await NotificationService.check_subscription_match(alert, subscription)
    assert matched is False


@pytest.mark.service
@pytest.mark.asyncio
async def test_check_subscription_match_allows_system_alert_datasource_zero():
    alert = SimpleNamespace(datasource_id=0, severity="high")
    subscription = SimpleNamespace(
        datasource_ids=[1],
        severity_levels=["high"],
        time_ranges=[],
    )
    matched = await NotificationService.check_subscription_match(alert, subscription)
    assert matched is True


@pytest.mark.service
@pytest.mark.asyncio
async def test_check_subscription_match_within_time_range(mocker):
    mocker.patch("backend.services.notification_service.now", return_value=datetime(2026, 4, 27, 10, 30, 0))
    alert = SimpleNamespace(datasource_id=1, severity="high")
    subscription = SimpleNamespace(
        datasource_ids=[1],
        severity_levels=["high"],
        time_ranges=[{"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00"}],
    )
    matched = await NotificationService.check_subscription_match(alert, subscription)
    assert matched is True


@pytest.mark.service
@pytest.mark.asyncio
async def test_check_subscription_match_outside_time_range_returns_false(mocker):
    mocker.patch("backend.services.notification_service.now", return_value=datetime(2026, 4, 27, 20, 30, 0))
    alert = SimpleNamespace(datasource_id=1, severity="high")
    subscription = SimpleNamespace(
        datasource_ids=[1],
        severity_levels=["high"],
        time_ranges=[{"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00"}],
    )
    matched = await NotificationService.check_subscription_match(alert, subscription)
    assert matched is False


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_notifications_returns_empty_without_targets():
    db = AsyncMock()
    alert = SimpleNamespace(id=1)
    subscription = SimpleNamespace(id=100, integration_targets=[])

    logs = await NotificationService.send_notifications(db, alert, subscription)

    assert logs == []


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_notifications_delegates_to_dispatcher(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(id=1)
    subscription = SimpleNamespace(id=100, integration_targets=[{"integration_id": 1}])
    expected = [SimpleNamespace(status="sent")]
    dispatcher = mocker.patch(
        "backend.services.notification_dispatcher._send_via_integration",
        AsyncMock(return_value=expected),
    )

    logs = await NotificationService.send_notifications(db, alert, subscription)

    assert logs == expected
    dispatcher.assert_awaited_once_with(db, alert, subscription)


@pytest.mark.unit
def test_map_helpers_fallback_to_original_value():
    assert NotificationService._map_severity("critical") == "严重"
    assert NotificationService._map_severity("unknown") == "unknown"
    assert NotificationService._map_alert_type("system_error") == "系统错误"
    assert NotificationService._map_alert_type("custom") == "custom"


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_email_marks_failed_when_smtp_config_incomplete():
    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    db.execute = AsyncMock(return_value=_ConfigResult([]))

    log = await NotificationService._send_email(db, _alert(), "ops@example.com", 10)

    assert log.status == "failed"
    assert "SMTP configuration incomplete" in log.error_message
    assert added == [log]
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(log)


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_sms_marks_failed_when_webhook_missing():
    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    db.execute = AsyncMock(
        return_value=_ConfigResult([SimpleNamespace(key="sms_provider", value="webhook")])
    )

    log = await NotificationService._send_sms(db, _alert(), "13800000000", 20)

    assert log.status == "failed"
    assert "SMS webhook URL not configured" in log.error_message
    assert added == [log]
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(log)


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_phone_marks_failed_for_unsupported_provider():
    added = []
    db = AsyncMock()
    db.add = lambda obj: added.append(obj)
    db.execute = AsyncMock(
        return_value=_ConfigResult([SimpleNamespace(key="phone_provider", value="twilio")])
    )

    log = await NotificationService._send_phone(db, _alert(), "13800000000", 30)

    assert log.status == "failed"
    assert "Phone provider twilio not implemented" in log.error_message
    assert added == [log]
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(log)


@pytest.mark.service
@pytest.mark.asyncio
async def test_send_recovery_notifications_is_deprecated_noop():
    logs = await NotificationService.send_recovery_notifications(
        AsyncMock(),
        _alert(),
        SimpleNamespace(id=99),
    )

    assert logs == []
