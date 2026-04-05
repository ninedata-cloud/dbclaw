from datetime import datetime
from types import SimpleNamespace

from backend.models.alert_message import AlertMessage
from backend.services.notification_service import NotificationService


def _make_alert(severity: str) -> AlertMessage:
    alert = AlertMessage()
    alert.datasource_id = 1
    alert.alert_type = "threshold_violation"
    alert.severity = severity
    alert.title = "CPU使用率过高"
    alert.content = "测试告警"
    alert.metric_name = "cpu_usage"
    alert.metric_value = 95.0
    alert.threshold_value = 80.0
    alert.trigger_reason = "CPU超过阈值"
    alert.created_at = datetime(2026, 3, 25, 10, 0, 0)
    return alert


def _make_datasource():
    return SimpleNamespace(name="prod-db", db_type="mysql", host="127.0.0.1", port=3306)


def test_feishu_payload_high_uses_red_header():
    payload = NotificationService._build_feishu_payload(_make_alert("HIGH"), _make_datasource())
    assert payload["card"]["header"]["template"] == "red"


def test_feishu_payload_medium_uses_orange_header():
    payload = NotificationService._build_feishu_payload(_make_alert("MEDIUM"), _make_datasource())
    assert payload["card"]["header"]["template"] == "orange"


def test_feishu_payload_low_uses_orange_header():
    payload = NotificationService._build_feishu_payload(_make_alert("LOW"), _make_datasource())
    assert payload["card"]["header"]["template"] == "orange"
