from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.models.alert_event  # noqa: F401
import backend.models.alert_message  # noqa: F401
import backend.models.datasource  # noqa: F401
from backend.database import Base
from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.models.datasource import Datasource
from backend.services.alert_statistics_service import query_alert_statistics


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


async def _seed_datasource(db_session, name: str, port: int) -> Datasource:
    datasource = Datasource(
        name=name,
        db_type="mysql",
        host="127.0.0.1",
        port=port,
        username="root",
        database=name,
        is_active=True,
    )
    db_session.add(datasource)
    await db_session.commit()
    await db_session.refresh(datasource)
    return datasource


@pytest.mark.asyncio
async def test_query_alert_statistics_events_scope_returns_overview_trend_and_topn(db_session):
    ds1 = await _seed_datasource(db_session, "orders", 3306)
    ds2 = await _seed_datasource(db_session, "analytics", 3307)

    events = [
        AlertEvent(
            datasource_id=ds1.id,
            aggregation_key=f"{ds1.id}:cpu_usage",
            aggregation_type="by_metric_name",
            first_alert_id=1,
            latest_alert_id=1,
            alert_count=2,
            event_start_time=datetime(2026, 4, 10, 10, 5, 0),
            event_end_time=datetime(2026, 4, 10, 10, 20, 0),
            last_updated=datetime(2026, 4, 10, 10, 20, 0),
            status="active",
            severity="critical",
            title="CPU 阈值告警",
            alert_type="threshold_violation",
            metric_name="cpu_usage",
            event_category="performance",
            fault_domain="performance",
        ),
        AlertEvent(
            datasource_id=ds1.id,
            aggregation_key=f"{ds1.id}:disk_usage",
            aggregation_type="by_metric_name",
            first_alert_id=2,
            latest_alert_id=2,
            alert_count=1,
            event_start_time=datetime(2026, 4, 10, 11, 0, 0),
            event_end_time=datetime(2026, 4, 10, 11, 20, 0),
            last_updated=datetime(2026, 4, 10, 11, 20, 0),
            status="resolved",
            severity="high",
            title="磁盘阈值告警",
            alert_type="threshold_violation",
            metric_name="disk_usage",
            event_category="storage",
            fault_domain="storage",
        ),
        AlertEvent(
            datasource_id=ds2.id,
            aggregation_key=f"{ds2.id}:connections",
            aggregation_type="by_metric_name",
            first_alert_id=3,
            latest_alert_id=3,
            alert_count=3,
            event_start_time=datetime(2026, 4, 10, 12, 10, 0),
            event_end_time=datetime(2026, 4, 10, 12, 40, 0),
            last_updated=datetime(2026, 4, 10, 12, 40, 0),
            status="acknowledged",
            severity="medium",
            title="连接数告警",
            alert_type="system_error",
            metric_name="connections",
            event_category="availability",
            fault_domain="availability",
        ),
    ]
    db_session.add_all(events)
    await db_session.commit()

    result = await query_alert_statistics(
        db_session,
        scope="events",
        start_time="2026-04-10 09:00:00",
        end_time="2026-04-10 13:00:00",
        bucket="1h",
        top_n=2,
    )

    assert result["success"] is True
    assert result["overview"]["total"] == 3
    assert result["overview"]["unique_datasource"] == 2
    assert result["time_range"]["bucket"] == "1h"
    assert result["by_severity"][0]["value"] == "critical"
    assert any(item["value"] == "performance" for item in result["by_event_category"])
    assert len(result["trend"]) == 3
    assert result["top_datasource"][0]["datasource_id"] == ds1.id
    assert result["top_metrics"][0]["value"] == "connections" or result["top_metrics"][0]["value"] == "cpu_usage"


@pytest.mark.asyncio
async def test_query_alert_statistics_alert_scope_applies_filters_and_joins_event_dimensions(db_session):
    ds1 = await _seed_datasource(db_session, "payments", 3310)
    ds2 = await _seed_datasource(db_session, "report", 3311)

    event1 = AlertEvent(
        datasource_id=ds1.id,
        aggregation_key=f"{ds1.id}:cpu_usage",
        aggregation_type="by_metric_name",
        first_alert_id=1,
        latest_alert_id=2,
        alert_count=2,
        event_start_time=datetime(2026, 4, 11, 8, 0, 0),
        event_end_time=datetime(2026, 4, 11, 8, 30, 0),
        last_updated=datetime(2026, 4, 11, 8, 30, 0),
        status="active",
        severity="high",
        title="CPU 告警事件",
        alert_type="threshold_violation",
        metric_name="cpu_usage",
        event_category="performance",
        fault_domain="performance",
    )
    event2 = AlertEvent(
        datasource_id=ds2.id,
        aggregation_key=f"{ds2.id}:disk_usage",
        aggregation_type="by_metric_name",
        first_alert_id=3,
        latest_alert_id=3,
        alert_count=1,
        event_start_time=datetime(2026, 4, 11, 9, 0, 0),
        event_end_time=datetime(2026, 4, 11, 9, 10, 0),
        last_updated=datetime(2026, 4, 11, 9, 10, 0),
        status="resolved",
        severity="low",
        title="磁盘告警事件",
        alert_type="threshold_violation",
        metric_name="disk_usage",
        event_category="storage",
        fault_domain="storage",
    )
    db_session.add_all([event1, event2])
    await db_session.commit()
    await db_session.refresh(event1)
    await db_session.refresh(event2)

    alerts = [
        AlertMessage(
            datasource_id=ds1.id,
            alert_type="threshold_violation",
            severity="high",
            title="CPU 告警 1",
            content="CPU > 80",
            metric_name="cpu_usage",
            status="active",
            event_id=event1.id,
            created_at=datetime(2026, 4, 11, 8, 5, 0),
            updated_at=datetime(2026, 4, 11, 8, 5, 0),
        ),
        AlertMessage(
            datasource_id=ds1.id,
            alert_type="threshold_violation",
            severity="high",
            title="CPU 告警 2",
            content="CPU > 90",
            metric_name="cpu_usage",
            status="active",
            event_id=event1.id,
            created_at=datetime(2026, 4, 11, 8, 20, 0),
            updated_at=datetime(2026, 4, 11, 8, 20, 0),
        ),
        AlertMessage(
            datasource_id=ds2.id,
            alert_type="threshold_violation",
            severity="low",
            title="磁盘告警",
            content="disk > 90",
            metric_name="disk_usage",
            status="resolved",
            event_id=event2.id,
            created_at=datetime(2026, 4, 11, 9, 5, 0),
            updated_at=datetime(2026, 4, 11, 9, 5, 0),
            resolved_at=datetime(2026, 4, 11, 9, 15, 0),
        ),
    ]
    db_session.add_all(alerts)
    await db_session.commit()

    result = await query_alert_statistics(
        db_session,
        scope="alerts",
        datasource_ids=[ds1.id],
        start_time="2026-04-11 07:00:00",
        end_time="2026-04-11 10:00:00",
        status="active",
        bucket="1h",
        top_n=3,
    )

    assert result["success"] is True
    assert result["overview"]["total"] == 2
    assert result["overview"]["active"] == 2
    assert result["top_datasource"][0]["datasource_id"] == ds1.id
    assert result["top_metrics"][0]["value"] == "cpu_usage"
    assert result["by_fault_domain"] == [{"value": "performance", "count": 2}]
    assert result["by_event_category"] == [{"value": "performance", "count": 2}]
    assert len(result["trend"]) == 1
