from datetime import datetime
from types import SimpleNamespace

from backend.services.alert_service import (
    build_alert_title_and_content,
    extract_connection_failure_detail,
)
from backend.services.notification_dispatcher import (
    _build_active_alert_payload,
    _build_recovery_alert_payload,
)


def _make_connection_alert():
    return SimpleNamespace(
        id=101,
        alert_type="system_error",
        severity="critical",
        metric_name="connection_status",
        metric_value=0.0,
        threshold_value=1.0,
        trigger_reason="数据库连接失败：timeout after 5s",
        content="状态：数据库连接失败\n错误详情：timeout after 5s",
        created_at=datetime(2026, 4, 6, 15, 24, 31),
        resolved_at=datetime(2026, 4, 6, 15, 25, 19),
        resolved_value=1.0,
    )


def test_connection_alert_title_and_content_are_human_friendly():
    title, content = build_alert_title_and_content(
        alert_type="system_error",
        metric_name="connection_status",
        metric_value=0.0,
        threshold_value=1.0,
        trigger_reason="数据库连接失败：timeout after 5s",
    )

    assert title == "数据库连接失败"
    assert content == "状态：数据库连接失败\n错误详情：timeout after 5s"


def test_ai_policy_alert_title_uses_friendly_display_name():
    title, content = build_alert_title_and_content(
        alert_type="ai_policy_violation",
        metric_name="AI 智能判警",
        metric_value=None,
        threshold_value=None,
        trigger_reason="CPU、连接数持续升高，AI 判定风险较高",
    )

    assert title == "AI 智能判警告警"
    assert content == "原因：CPU、连接数持续升高，AI 判定风险较高"


def test_extract_connection_failure_detail_strips_generic_prefix():
    assert extract_connection_failure_detail("Connection failed: socket closed") == "socket closed"
    assert extract_connection_failure_detail("数据库连接失败：timeout") == "timeout"
    assert extract_connection_failure_detail("数据库连接失败") is None


def test_connection_failure_notification_payload_uses_failure_language():
    alert = _make_connection_alert()
    datasource = SimpleNamespace(name="vastbase(132)")

    payload = _build_active_alert_payload(
        alert,
        datasource,
        {"summary": None, "root_cause": None, "recommended_actions": None, "status": None},
        alert_url=None,
        report_url=None,
    )

    assert payload["title"] == "【CRITICAL】vastbase(132) 数据库连接失败"
    assert payload["alert_type"] == "连接失败"
    assert payload["metric_name"] is None
    assert payload["threshold_value"] is None
    assert payload["trigger_reason"] == "timeout after 5s"
    assert "数据库连接失败" in payload["content"]


def test_connection_recovery_notification_payload_uses_recovery_language():
    alert = _make_connection_alert()
    datasource = SimpleNamespace(name="vastbase(132)")

    payload = _build_recovery_alert_payload(alert, datasource)

    assert payload["title"] == "【已恢复】vastbase(132) 数据库连接已恢复"
    assert payload["alert_type"] == "连接恢复"
    assert payload["metric_name"] is None
    assert payload["threshold_value"] is None
    assert payload["trigger_reason"] == "timeout after 5s"
    assert payload["content"].startswith("状态：数据库连接已恢复")
    assert "恢复时间：2026-04-06 15:25:19" in payload["content"]
