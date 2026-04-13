from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.aggregation_engine import AggregationEngine
from backend.services.alert_service import _build_alert_diagnosis_draft
from backend.services.inspection_service import InspectionService
from backend.utils.datetime_helper import now


@pytest.mark.asyncio
async def test_trigger_inspection_skips_recent_connection_failure_trigger():
    service = InspectionService(db_session_factory=None)
    db = AsyncMock(spec=AsyncSession)

    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(id=77)
    db.execute.return_value = result

    with patch("backend.services.inspection_service._get_trigger_dedup_window_minutes", return_value=60):
        trigger_id = await service.trigger_inspection(
            db=db,
            datasource_id=5,
            trigger_type="connection_failure",
            reason="Database connection failed: timeout after 5s",
        )

    assert trigger_id == 77
    db.add.assert_not_called()

    query_text = str(db.execute.call_args.args[0])
    assert "inspection_triggers.datasource_id =" in query_text
    assert "inspection_triggers.trigger_type =" in query_text
    assert "inspection_triggers.triggered_at >=" in query_text


@pytest.mark.asyncio
async def test_aggregation_rule_suppresses_recent_recurrence_within_cooldown():
    db = AsyncMock(spec=AsyncSession)
    recent_delivery = SimpleNamespace(
        sent_at=now() - timedelta(minutes=6),
        created_at=now() - timedelta(minutes=6),
    )
    result = MagicMock()
    result.all.return_value = [(recent_delivery, "critical")]
    db.execute.return_value = result

    alert = SimpleNamespace(
        id=101,
        datasource_id=9,
        alert_type="system_error",
        metric_name="connection_status",
        event_id=None,
        severity="critical",
    )
    subscription = SimpleNamespace(id=3, aggregation_script=None)

    with patch.object(
        AggregationEngine,
        "_get_notification_cooldown_minutes",
        new=AsyncMock(return_value=60),
    ):
        should_send = await AggregationEngine._default_aggregation_rule(db, alert, subscription)

    assert should_send is False

    query_text = str(db.execute.call_args.args[0])
    assert "alert_messages.alert_type =" in query_text
    assert "alert_messages.metric_name =" in query_text


@pytest.mark.asyncio
async def test_aggregation_rule_allows_severity_escalation_within_cooldown():
    db = AsyncMock(spec=AsyncSession)
    recent_delivery = SimpleNamespace(
        sent_at=now() - timedelta(minutes=6),
        created_at=now() - timedelta(minutes=6),
    )
    result = MagicMock()
    result.all.return_value = [(recent_delivery, "medium")]
    db.execute.return_value = result

    alert = SimpleNamespace(
        id=102,
        datasource_id=9,
        alert_type="system_error",
        metric_name="connection_status",
        event_id=None,
        severity="critical",
    )
    subscription = SimpleNamespace(id=3, aggregation_script=None)

    with patch.object(
        AggregationEngine,
        "_get_notification_cooldown_minutes",
        new=AsyncMock(return_value=60),
    ):
        should_send = await AggregationEngine._default_aggregation_rule(db, alert, subscription)

    assert should_send is True


@pytest.mark.asyncio
async def test_notification_cooldown_reads_dedicated_config():
    db = AsyncMock(spec=AsyncSession)

    with patch("backend.services.config_service.get_config", new=AsyncMock(return_value=90)):
        cooldown = await AggregationEngine._get_notification_cooldown_minutes(db)

    assert cooldown == 90


def test_build_alert_diagnosis_draft_includes_latest_error_context():
    event = SimpleNamespace(
        title="数据库连接失败",
        severity="critical",
        alert_type="system_error",
        metric_name="connection_status",
        event_start_time=now() - timedelta(minutes=4),
    )
    datasource = SimpleNamespace(
        name="polardb-oracle_14",
        db_type="oracle",
        host="192.168.2.132",
        port=1523,
    )
    latest_alert = SimpleNamespace(
        metric_name="connection_status",
        metric_value=0.0,
        threshold_value=1.0,
        trigger_reason="数据库连接失败：timeout after 5s",
        content="状态：数据库连接失败\n错误详情：timeout after 5s",
    )

    draft = _build_alert_diagnosis_draft(
        event,
        datasource=datasource,
        latest_alert=latest_alert,
        include_now_suffix=True,
    )

    assert "数据库：polardb-oracle_14 / oracle / 192.168.2.132:1523" in draft
    assert "最近触发原因：数据库连接失败：timeout after 5s" in draft
    assert "最近告警内容：状态：数据库连接失败 错误详情：timeout after 5s" in draft
