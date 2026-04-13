import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from backend.routers.inspections import AlertTemplateSchema
from backend.services.alert_template_service import (
    normalize_alert_template_config,
    reset_inspection_config_to_template,
    summarize_alert_template_config,
)


def test_normalize_alert_template_config_clears_legacy_ai_template_binding():
    normalized = normalize_alert_template_config({
        "alert_engine_mode": "threshold",
        "ai_policy_text": "legacy rule",
        "ai_policy_id": 12,
        "alert_ai_model_id": 8,
        "ai_shadow_enabled": True,
    })

    assert normalized["alert_engine_mode"] == "threshold"
    assert normalized["ai_policy_text"] is None
    assert normalized["alert_ai_model_id"] is None
    assert normalized["ai_shadow_enabled"] is False


def test_normalize_alert_template_config_keeps_inline_ai_rule():
    normalized = normalize_alert_template_config({
        "alert_engine_mode": "ai",
        "ai_policy_text": "当 CPU 持续升高时触发告警",
        "alert_ai_model_id": 3,
    })

    assert normalized["alert_engine_mode"] == "ai"
    assert normalized["ai_policy_text"] == "当 CPU 持续升高时触发告警"
    assert normalized["alert_ai_model_id"] == 3


def test_alert_template_schema_requires_ai_rule_for_ai_mode():
    with pytest.raises(ValidationError):
        AlertTemplateSchema(
            name="AI 模板",
            template_config={
                "alert_engine_mode": "ai",
                "ai_policy_text": "   ",
            },
        )


def test_alert_template_summary_supports_custom_expression():
    summary = summarize_alert_template_config({
        "alert_engine_mode": "threshold",
        "threshold_rules": {
            "custom_expression": {
                "expression": "cpu_usage > 80 and connections > 120",
                "duration": 60,
            },
        },
    })

    assert "表达式" in summary
    assert "cpu_usage > 80" in summary


def test_reset_inspection_config_to_template_clears_legacy_fields():
    template = SimpleNamespace(id=3)
    config = SimpleNamespace(
        alert_template_id=None,
        threshold_rules={"cpu_usage": {"threshold": 95, "duration": 60}},
        alert_engine_mode="ai",
        ai_policy_source="template",
        ai_policy_text="legacy",
        ai_policy_id=12,
        alert_ai_model_id=8,
        ai_shadow_enabled=True,
        baseline_config={"enabled": True},
        event_ai_config={"enabled": True},
    )

    changed = reset_inspection_config_to_template(config, template)

    assert changed is True
    assert config.alert_template_id == 3
    assert config.threshold_rules == {}
    assert config.alert_engine_mode == "inherit"
    assert config.ai_policy_source == "inline"
    assert config.ai_policy_text is None
    assert config.ai_policy_id is None
    assert config.alert_ai_model_id is None
    assert config.ai_shadow_enabled is False
    assert config.baseline_config == {}
    assert config.event_ai_config == {}
