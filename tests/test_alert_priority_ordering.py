from datetime import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.schemas.alert import AlertQueryParams
from backend.services.alert_event_service import AlertEventService
from backend.services.alert_service import AlertService


class FakeScalarSequence:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class FakeQueryResult:
    def __init__(self, *, scalar_value=None, items=None):
        self._scalar_value = scalar_value
        self._items = list(items or [])

    def scalar(self):
        return self._scalar_value

    def scalars(self):
        return FakeScalarSequence(self._items)


class FakeOrderedSession:
    def __init__(self, items, *, sort_key, count_mode: str):
        self._items = list(items)
        self._sort_key = sort_key
        self._count_mode = count_mode
        self._execute_calls = 0

    async def execute(self, statement):
        del statement
        self._execute_calls += 1
        if self._execute_calls == 1:
            if self._count_mode == "scalar":
                return FakeQueryResult(scalar_value=len(self._items))
            return FakeQueryResult(items=self._items)
        ordered = sorted(self._items, key=self._sort_key)
        return FakeQueryResult(items=ordered)


def _event_sort_key(event: AlertEvent):
    status_priority = {"active": 0, "acknowledged": 1}
    return (
        status_priority.get(event.status, 2),
        -event.event_start_time.timestamp(),
        -(event.id or 0),
    )


def _alert_sort_key(alert: AlertMessage):
    status_priority = {"active": 0, "acknowledged": 1}
    return (
        status_priority.get(alert.status, 2),
        -alert.created_at.timestamp(),
        -(alert.id or 0),
    )


@pytest.mark.asyncio
async def test_alert_event_prioritize_active_before_resolved():
    fake_db = FakeOrderedSession(
        [
            AlertEvent(
                id=1,
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
                id=2,
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
                id=3,
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
                id=4,
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
        ],
        sort_key=_event_sort_key,
        count_mode="scalar",
    )

    events, total = await AlertEventService.get_events(fake_db, limit=10, offset=0, status="all")

    assert total == 4
    assert [event.title for event in events] == [
        "active-newer",
        "active-older",
        "acknowledged",
        "resolved-newest",
    ]


@pytest.mark.asyncio
async def test_alert_message_prioritize_active_before_resolved():
    fake_db = FakeOrderedSession(
        [
            AlertMessage(
                id=1,
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
                id=2,
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
                id=3,
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
        ],
        sort_key=_alert_sort_key,
        count_mode="scalars",
    )

    alerts, total = await AlertService.get_alerts(
        fake_db,
        AlertQueryParams(status="all", limit=10, offset=0),
    )

    assert total == 3
    assert [alert.title for alert in alerts] == [
        "active-connection",
        "acknowledged-cpu",
        "resolved-newest",
    ]
