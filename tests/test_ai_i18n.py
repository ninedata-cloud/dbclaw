from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.agent.conversation_skills import (
    _build_plan_summary,
    _keyword_assess_risk,
    _sanitize_report_markdown,
    generate_report_with_skills,
)
from backend.agent.prompts import (
    DIAGNOSTIC_PROMPT,
    REPORT_GENERATION_PROMPT,
    apply_ai_output_language,
    build_ai_language_instruction,
)
from backend.services.alert_ai_service import (
    AI_DECISION_ALERT,
    _compress_alert_ai_evidence,
    _compress_alert_ai_reason,
)
from backend.services.chat_orchestration_service import (
    _extract_section_lines,
    apply_render_segments_event,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def test_ai_language_instruction_uses_explicit_product_locale():
    english = build_ai_language_instruction("en-US")
    chinese = build_ai_language_instruction("zh-CN")

    assert "English (US)" in english
    assert "product context" in english
    assert "Simplified Chinese" in chinese
    assert apply_ai_output_language(DIAGNOSTIC_PROMPT, "en-US").endswith(english)
    assert apply_ai_output_language(DIAGNOSTIC_PROMPT, None) == DIAGNOSTIC_PROMPT


def test_prompts_no_longer_force_chinese_reports_or_diagnostic_plans():
    assert "用简洁中文输出诊断计划" not in DIAGNOSTIC_PROMPT
    assert "必须使用中文撰写整个报告" not in REPORT_GENERATION_PROMPT
    assert "目标输出语言" in DIAGNOSTIC_PROMPT
    assert "目标输出语言" in REPORT_GENERATION_PROMPT


def test_english_plan_and_risk_messages_are_localized():
    plan = _build_plan_summary("diagnostic", "performance", [], "en-US")
    risk = _keyword_assess_risk(
        "execute_sql",
        {"sql": "DROP TABLE old_events"},
        ["execute_any_sql"],
        "en-US",
    )

    assert plan.startswith("Diagnostic plan started:")
    assert "performance issue" in plan
    assert risk["level"] == "destructive"
    assert "may directly modify or destroy" in risk["risk_reason"]


def test_english_render_segments_and_report_sanitizing():
    segments = apply_render_segments_event(
        [],
        {
            "type": "tool_call",
            "tool_call_id": "call-1",
            "tool_name": "get_metrics",
            "tool_args": {},
            "locale": "en-US",
        },
    )
    assert segments[0]["summary"] == "Call started; waiting for the result"

    report = _sanitize_report_markdown(
        "I will generate a database report\n\n# Database Inspection Report\n\n## Executive Summary\n\nHealthy"
    )
    assert report.startswith("# Database Inspection Report")
    assert "I will generate" not in report

    findings = _extract_section_lines(
        "### Diagnostic Conclusion\n- Connection pool exhaustion\n\n### Key Evidence\n- 100 active connections",
        ["diagnostic conclusion", "conclusion"],
    )
    assert findings == ["Connection pool exhaustion"]


def test_alert_ai_preserves_english_reason_and_evidence():
    rule = "Trigger a high alert when CPU usage stays above 90 percent for five minutes."
    reason = _compress_alert_ai_reason(
        decision=AI_DECISION_ALERT,
        severity="high",
        reason="CPU usage stayed above 90 percent for five minutes, triggering a high alert.",
        reference_text=rule,
    )
    evidence = _compress_alert_ai_evidence(
        ["CPU usage remained above the configured threshold."],
        reference_text=rule,
    )

    assert "触发" not in reason
    assert "CPU usage" in reason
    assert evidence == ["CPU usage remained above the configured threshold."]


@pytest.mark.asyncio
async def test_report_generation_passes_locale_to_conversation(mocker):
    captured = {}

    async def fake_conversation(**kwargs):
        captured.update(kwargs)
        yield {"type": "content", "content": "# Database Inspection Report\n\n## Executive Summary\n\nHealthy"}
        yield {"type": "done"}

    mocker.patch(
        "backend.agent.conversation_skills.run_conversation_with_skills",
        fake_conversation,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(None)))

    result = await generate_report_with_skills(
        datasource_id=7,
        datasource_name="primary",
        datasource_type="postgresql",
        trigger_reason="Manual inspection",
        system_prompt=REPORT_GENERATION_PROMPT,
        db=db,
        locale="en-US",
    )

    assert result["status"] == "completed"
    assert captured["locale"] == "en-US"
    assert captured["messages"][0]["content"].startswith("Generate a comprehensive inspection report")
