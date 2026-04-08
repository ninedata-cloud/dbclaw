import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.schemas.alert import AlertQueryParams
from backend.services.alert_event_service import AlertEventService
from backend.services.alert_service import AlertService


@pytest.mark.asyncio
async def test_alert_events_prioritize_active_before_resolved(tmp_path):
    db_path = tmp_path / "alert-events-order.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(AlertEvent.__table__.create)

    async with session_factory() as db:
        db.add_all([
            AlertEvent(
                datasource_id=1,
                aggregation_key="1:cpu_usage",
                aggregation_type="by_metric_name",
                first_alert_id=11,
                latest_alert_id=11,
                alert_count=1,
                event_start_time=datetime(2026, 4, 2, 10, 0, 0),
                event_end_time=datetime(2026, 4, 2, 10, 0, 0),
                last_updated=datetime(2026, 4, 2, 10, 0, 0),
                status="active",
                severity="high",
                title="active-newer",
                alert_type="threshold_violation",
                metric_name="cpu_usage",
            ),
            AlertEvent(
                datasource_id=1,
                aggregation_key="1:memory_usage",
                aggregation_type="by_metric_name",
                first_alert_id=12,
                latest_alert_id=12,
                alert_count=1,
                event_start_time=datetime(2026, 4, 1, 10, 0, 0),
                event_end_time=datetime(2026, 4, 1, 10, 0, 0),
                last_updated=datetime(2026, 4, 1, 10, 0, 0),
                status="active",
                severity="medium",
                title="active-older",
                alert_type="threshold_violation",
                metric_name="memory_usage",
            ),
            AlertEvent(
                datasource_id=1,
                aggregation_key="1:connection_status",
                aggregation_type="by_metric_name",
                first_alert_id=13,
                latest_alert_id=13,
                alert_count=1,
                event_start_time=datetime(2026, 4, 3, 10, 0, 0),
                event_end_time=datetime(2026, 4, 3, 10, 0, 0),
                last_updated=datetime(2026, 4, 3, 10, 0, 0),
                status="acknowledged",
                severity="critical",
                title="acknowledged",
                alert_type="system_error",
                metric_name="connection_status",
            ),
            AlertEvent(
                datasource_id=1,
                aggregation_key="1:disk_usage",
                aggregation_type="by_metric_name",
                first_alert_id=14,
                latest_alert_id=14,
                alert_count=1,
                event_start_time=datetime(2026, 4, 6, 10, 0, 0),
                event_end_time=datetime(2026, 4, 6, 10, 0, 0),
                last_updated=datetime(2026, 4, 6, 10, 0, 0),
                status="resolved",
                severity="low",
                title="resolved-newest",
                alert_type="threshold_violation",
                metric_name="disk_usage",
            ),
        ])
        await db.commit()

        events, total = await AlertEventService.get_events(db, limit=10, offset=0, status="all")

        assert total == 4
        assert [event.title for event in events] == [
            "active-newer",
            "active-older",
            "acknowledged",
            "resolved-newest",
        ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_alert_messages_prioritize_active_before_resolved(tmp_path):
    db_path = tmp_path / "alert-messages-order.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(AlertMessage.__table__.create)

    async with session_factory() as db:
        db.add_all([
            AlertMessage(
                datasource_id=1,
                alert_type="system_error",
                severity="critical",
                title="active-connection",
                content="active",
                metric_name="connection_status",
                status="active",
                created_at=datetime(2026, 4, 1, 12, 42, 0),
                updated_at=datetime(2026, 4, 1, 12, 42, 0),
            ),
            AlertMessage(
                datasource_id=1,
                alert_type="threshold_violation",
                severity="high",
                title="acknowledged-cpu",
                content="ack",
                metric_name="cpu_usage",
                status="acknowledged",
                created_at=datetime(2026, 4, 2, 12, 42, 0),
                updated_at=datetime(2026, 4, 2, 12, 42, 0),
            ),
            AlertMessage(
                datasource_id=1,
                alert_type="threshold_violation",
                severity="low",
                title="resolved-newest",
                content="resolved",
                metric_name="disk_usage",
                status="resolved",
                created_at=datetime(2026, 4, 6, 12, 42, 0),
                updated_at=datetime(2026, 4, 6, 12, 42, 0),
            ),
        ])
        await db.commit()

        alerts, total = await AlertService.get_alerts(
            db,
            AlertQueryParams(status="all", limit=10, offset=0),
        )

        assert total == 3
        assert [alert.title for alert in alerts] == [
            "active-connection",
            "acknowledged-cpu",
            "resolved-newest",
        ]

    await engine.dispose()
