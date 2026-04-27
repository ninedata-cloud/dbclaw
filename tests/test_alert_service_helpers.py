from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import alert_service
from backend.services.alert_service import (
    AlertService,
    build_alert_display_metric_name,
    build_alert_display_title,
    build_alert_title_and_content,
    extract_connection_failure_detail,
    is_connection_status_alert,
    normalize_alert_diagnosis_fields,
    normalize_event_ai_config,
    should_refresh_event_diagnosis,
)
from backend.utils.datetime_helper import now


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._value)


@pytest.mark.unit
def test_strip_and_extract_markdown_sections():
    text = """
## 根本原因
- 数据库连接池耗尽

## 处置建议
1. 扩容连接池
"""
    sections = alert_service._extract_sections(text)
    assert "根本原因" in sections
    assert "处置建议" in sections
    assert alert_service._find_section_content(sections, ["根本原因"]) is not None


@pytest.mark.unit
def test_extract_keyword_block_handles_plain_text():
    text = "根本原因：连接池过小\n\n其他说明"
    block = alert_service._extract_keyword_block(text, ["根本原因"])
    assert block == "连接池过小"


@pytest.mark.unit
def test_clean_section_text_deduplicates_and_skips_process_lines():
    cleaned = alert_service._clean_section_text(
        "1. 让我先分析\n2. 连接池过小\n3. 连接池过小\n4. 增加最大连接数",
        max_lines=3,
        max_chars=100,
    )
    assert cleaned == "连接池过小；增加最大连接数"


@pytest.mark.unit
def test_extract_root_and_action_sentence_from_free_text():
    text = "主要原因是连接池配置过低。建议先扩容连接池并优化慢查询。"
    root = alert_service._extract_root_cause_sentence(text)
    action = alert_service._extract_action_text(text)
    assert "连接池" in (root or "")
    assert "建议" in (action or "")


@pytest.mark.unit
def test_compact_summary_truncates_long_text():
    value = "A" * 200
    compact = alert_service._compact_summary_text(value, max_chars=60)
    assert compact is not None
    assert compact.endswith("...")
    assert len(compact) <= 63


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (10, "low"),
        (21, "medium"),
        (51, "high"),
        (101, "critical"),
    ],
)
def test_calculate_severity_levels(value, expected):
    assert AlertService.calculate_severity(value) == expected


@pytest.mark.unit
def test_connection_status_helpers_extract_detail():
    assert is_connection_status_alert("system_error", "connection_status") is True
    assert extract_connection_failure_detail("connection failed: timeout") == "timeout"
    assert extract_connection_failure_detail("数据库连接失败：认证失败") == "认证失败"


@pytest.mark.unit
def test_build_alert_title_and_content_for_connection_error():
    title, content = build_alert_title_and_content(
        alert_type="system_error",
        metric_name="connection_status",
        metric_value=None,
        threshold_value=None,
        trigger_reason="connection failed: too many connections",
    )
    assert title == "数据库连接失败"
    assert "too many connections" in content


@pytest.mark.unit
def test_ai_policy_display_title_prefers_reason():
    title = build_alert_display_title(
        alert_type="ai_policy_violation",
        title="AI 判警",
        metric_name="ai 判警",
        trigger_reason="CPU 持续高于阈值，AI 判定风险较高",
    )
    assert "CPU" in title


@pytest.mark.unit
def test_ai_policy_display_metric_name_uses_domain_fallback():
    metric_name = build_alert_display_metric_name(
        alert_type="ai_policy_violation",
        metric_name=None,
        trigger_reason="",
        fault_domain="replication",
    )
    assert metric_name == "复制异常"


@pytest.mark.unit
def test_normalize_alert_diagnosis_fields_extracts_root_and_actions():
    normalized = normalize_alert_diagnosis_fields(
        root_cause=None,
        recommended_actions=None,
        summary="""
## 根本原因
1. 慢查询导致连接堆积

## 处置建议
1. 增加索引
2. 优化慢 SQL
""",
    )
    assert "慢查询" in (normalized["root_cause"] or "")
    assert "增加索引" in (normalized["recommended_actions"] or "")
    assert normalized["summary"] is not None


@pytest.mark.unit
def test_normalize_event_ai_config_clamps_window():
    config = normalize_event_ai_config(
        {
            "enabled": False,
            "trigger_on_create": False,
            "trigger_on_severity_upgrade": True,
            "trigger_on_recovery": True,
            "stale_recheck_minutes": 2,
        }
    )
    assert config["enabled"] is False
    assert config["trigger_on_create"] is False
    assert config["stale_recheck_minutes"] == 5


@pytest.mark.unit
def test_normalize_prompt_and_datasource_prompt():
    normalized = alert_service._normalize_prompt_field("`CPU`   超高", max_chars=20)
    assert normalized == "CPU 超高"

    datasource = SimpleNamespace(
        name="prod-main",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
    )
    assert "prod-main" in (alert_service._format_datasource_prompt(datasource) or "")


@pytest.mark.unit
def test_build_alert_diagnosis_draft_contains_context():
    event = SimpleNamespace(
        severity="high",
        title="CPU 告警",
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        event_started_at=now(),
    )
    latest_alert = SimpleNamespace(
        metric_name="cpu_usage",
        metric_value=92,
        threshold_value=80,
        trigger_reason="CPU长期过高",
        content="CPU > 80%",
    )
    draft = alert_service._build_alert_diagnosis_draft(
        event,
        datasource=SimpleNamespace(name="prod", db_type="mysql", host="10.0.0.1", port=3306),
        latest_alert=latest_alert,
        include_now_suffix=True,
    )
    assert "CPU 告警" in draft
    assert "持续时间" in draft
    assert "根本原因" in draft


@pytest.mark.unit
def test_should_refresh_event_diagnosis_when_missing_summary():
    event = SimpleNamespace(ai_diagnosis_summary=None)
    assert should_refresh_event_diagnosis(event, {"enabled": True}) is True


@pytest.mark.unit
def test_should_refresh_event_diagnosis_with_stale_completed_at(mocker):
    base_time = now()
    mocker.patch.object(alert_service, "now", lambda: base_time)
    event = SimpleNamespace(
        ai_diagnosis_summary="已有总结",
        is_diagnosis_refresh_needed=False,
        diagnosis_trigger_reason=None,
        diagnosis_completed_at=base_time - timedelta(minutes=31),
        status="active",
    )
    assert should_refresh_event_diagnosis(event, {"stale_recheck_minutes": 30}) is True


@pytest.mark.service
@pytest.mark.asyncio
async def test_acknowledge_alert_updates_status_and_user(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(id=1, status="active", acknowledged_by=None, acknowledged_at=None, updated_at=None)
    mocker.patch.object(AlertService, "get_alert_by_id", AsyncMock(return_value=alert))

    result = await AlertService.acknowledge_alert(db, 1, user_id=9)

    assert result is alert
    assert alert.status == "acknowledged"
    assert alert.acknowledged_by == 9
    assert alert.acknowledged_at is not None
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(alert)


@pytest.mark.service
@pytest.mark.asyncio
async def test_acknowledge_alert_returns_none_when_missing(mocker):
    db = AsyncMock()
    mocker.patch.object(AlertService, "get_alert_by_id", AsyncMock(return_value=None))

    result = await AlertService.acknowledge_alert(db, 404, user_id=9)

    assert result is None
    db.commit.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_resolve_alert_sets_resolved_value_and_auto_resolves_event(mocker):
    db = AsyncMock()
    alert = SimpleNamespace(id=1, status="active", event_id=10, resolved_at=None, updated_at=None, resolved_value=None)
    mocker.patch.object(AlertService, "get_alert_by_id", AsyncMock(return_value=alert))
    auto_resolve = mocker.patch(
        "backend.services.alert_event_service.AlertEventService.check_and_auto_resolve_event",
        AsyncMock(return_value=SimpleNamespace(id=10)),
    )

    result = await AlertService.resolve_alert(db, 1, resolved_value=42.5)

    assert result is alert
    assert alert.status == "resolved"
    assert alert.resolved_value == 42.5
    auto_resolve.assert_awaited_once_with(db, 10)
    assert db.commit.await_count == 2
    db.refresh.assert_awaited_once_with(alert)


@pytest.mark.service
@pytest.mark.asyncio
async def test_resolve_alert_returns_none_when_missing(mocker):
    db = AsyncMock()
    mocker.patch.object(AlertService, "get_alert_by_id", AsyncMock(return_value=None))

    result = await AlertService.resolve_alert(db, 404)

    assert result is None
    db.commit.assert_not_awaited()


@pytest.mark.service
@pytest.mark.asyncio
async def test_get_user_subscriptions_returns_scalars_all():
    subscriptions = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(subscriptions))

    result = await AlertService.get_user_subscriptions(db, user_id=7)

    assert result == subscriptions


@pytest.mark.service
@pytest.mark.asyncio
async def test_update_subscription_converts_model_like_values_and_skips_none(mocker):
    db = AsyncMock()
    subscription = SimpleNamespace(
        id=1,
        datasource_ids=[],
        time_ranges=[],
        integration_targets=[],
        enabled=True,
        updated_at=None,
    )
    mocker.patch("backend.services.alert_service.get_alive_by_id", AsyncMock(return_value=subscription))
    time_range = SimpleNamespace(model_dump=lambda: {"start": "09:00", "end": "18:00", "days": [0]})
    target = SimpleNamespace(model_dump=lambda: {"target_id": "bot-1", "integration_id": 2, "name": "bot"})

    result = await AlertService.update_subscription(
        db,
        1,
        {
            "datasource_ids": [1, 2],
            "time_ranges": [time_range],
            "integration_targets": [target],
            "aggregation_script": None,
        },
    )

    assert result is subscription
    assert subscription.datasource_ids == [1, 2]
    assert subscription.time_ranges == [{"start": "09:00", "end": "18:00", "days": [0]}]
    assert subscription.integration_targets == [{"target_id": "bot-1", "integration_id": 2, "name": "bot"}]
    assert not hasattr(subscription, "aggregation_script")
    assert subscription.updated_at is not None
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(subscription)


@pytest.mark.service
@pytest.mark.asyncio
async def test_delete_subscription_soft_deletes_when_found(mocker):
    db = AsyncMock()
    subscription = SimpleNamespace(id=1, updated_at=None, soft_delete=mocker.Mock())
    mocker.patch("backend.services.alert_service.get_alive_by_id", AsyncMock(return_value=subscription))

    result = await AlertService.delete_subscription(db, 1, user_id=9)

    assert result is True
    subscription.soft_delete.assert_called_once_with(9)
    assert subscription.updated_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_delete_subscription_returns_false_when_missing(mocker):
    db = AsyncMock()
    mocker.patch("backend.services.alert_service.get_alive_by_id", AsyncMock(return_value=None))

    result = await AlertService.delete_subscription(db, 404, user_id=9)

    assert result is False
    db.commit.assert_not_awaited()
