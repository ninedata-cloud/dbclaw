from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.aggregation_engine import AggregationEngine


@pytest.mark.unit
def test_execute_sandboxed_requires_should_send():
    script = "def other_func(*args):\n    return True\n"
    with pytest.raises(ValueError, match="should_send"):
        AggregationEngine._execute_sandboxed(script, {}, [], 0, {})


@pytest.mark.unit
def test_execute_sandboxed_runs_user_logic():
    script = """
def should_send(alert_info, delivery_history, similar_alerts_count, current_time):
    return alert_info.get("severity") == "high" and similar_alerts_count < 3
"""
    result = AggregationEngine._execute_sandboxed(
        script,
        {"severity": "high"},
        [],
        1,
        {"hour": 10},
    )
    assert result is True


@pytest.mark.service
@pytest.mark.asyncio
async def test_should_send_alert_uses_custom_script_when_configured(mocker):
    db = AsyncMock()
    alert = SimpleNamespace()
    subscription = SimpleNamespace(aggregation_script="def should_send(*args): return True")
    execute_custom = mocker.patch.object(
        AggregationEngine,
        "execute_custom_script",
        AsyncMock(return_value=False),
    )
    default_rule = mocker.patch.object(
        AggregationEngine,
        "_default_aggregation_rule",
        AsyncMock(return_value=True),
    )

    should_send = await AggregationEngine.should_send_alert(db, alert, subscription)

    assert should_send is False
    execute_custom.assert_awaited_once()
    default_rule.assert_not_awaited()
