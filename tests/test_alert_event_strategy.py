from datetime import datetime
from types import SimpleNamespace

from backend.services.alert_event_service import hydrate_event_strategy_fields


def test_hydrate_event_strategy_fields_for_legacy_event():
    event = SimpleNamespace(
        alert_type="baseline_deviation",
        metric_name="cpu_usage",
        status="active",
        event_category=None,
        fault_domain=None,
        lifecycle_stage=None,
    )

    hydrate_event_strategy_fields(event)

    assert event.event_category == "performance" or event.event_category == "baseline"
    assert event.fault_domain == "performance"
    assert event.lifecycle_stage == "active"


def test_hydrate_event_strategy_fields_for_connection_failure():
    event = SimpleNamespace(
        alert_type="system_error",
        metric_name="connection_status",
        status="resolved",
        event_category=None,
        fault_domain=None,
        lifecycle_stage=None,
    )

    hydrate_event_strategy_fields(event)

    assert event.fault_domain == "availability"
    assert event.lifecycle_stage == "recovered"
