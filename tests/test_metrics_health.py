from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.routers import metrics as metrics_router


def test_merge_health_payloads_prefers_unhealthy_threshold_guard():
    threshold_health = {
        "healthy": False,
        "status": "critical",
        "violations": [{"type": "threshold", "metric": "disk_usage"}],
        "message": "检测到 1 个指标异常",
        "alert_engine": "threshold",
    }
    ai_health = {
        "healthy": True,
        "status": "healthy",
        "violations": [],
        "message": "证据不足，暂不告警",
        "alert_engine": "ai",
    }

    merged = metrics_router._merge_health_payloads(threshold_health, ai_health, alert_engine="ai")

    assert merged["healthy"] is False
    assert merged["violations"][0]["metric"] == "disk_usage"
    assert merged["alert_engine"] == "ai"


@pytest.mark.asyncio
async def test_build_effective_health_uses_threshold_guard_in_ai_mode():
    config = SimpleNamespace(
        threshold_rules={"disk_usage": {"threshold": 90, "duration": 600}},
        alert_engine_mode="ai",
    )
    metrics = {"disk_usage": 95}

    with patch(
        "backend.services.alert_ai_service.resolve_effective_alert_engine_mode",
        new=AsyncMock(return_value="ai"),
    ), patch.object(
        metrics_router,
        "_build_ai_health",
        new=AsyncMock(return_value={
            "healthy": True,
            "status": "healthy",
            "violations": [],
            "message": "AI 证据不足，暂不告警",
            "alert_engine": "ai",
        }),
    ):
        result = await metrics_router._build_effective_health(
            db=None,
            datasource_id=1,
            config=config,
            metrics=metrics,
        )

    assert result["healthy"] is False
    assert any(item.get("metric") == "disk_usage" for item in result["violations"])
