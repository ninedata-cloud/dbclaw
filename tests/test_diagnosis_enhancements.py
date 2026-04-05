from backend.agent.diagnosis_context import (
    build_focus_areas,
    extract_metric_signals,
    render_diagnostic_brief_for_prompt,
)
from backend.services.chat_orchestration_service import _build_diagnosis_event_payload


def test_extract_metric_signals_flags_high_risk_indicators():
    signals = extract_metric_signals(
        "db_status",
        {
            "threads_connected": 180,
            "max_connections": 200,
            "cache_hit_rate": 88.5,
            "slow_queries": 24,
            "innodb_row_lock_waits": 12,
        },
    )

    labels = {signal["label"] for signal in signals}
    assert "连接使用率" in labels
    assert "缓存命中率" in labels
    assert "慢查询数量" in labels
    assert "锁等待" in labels


def test_build_focus_areas_uses_category_signals_and_alerts():
    focus_areas = build_focus_areas(
        "performance",
        [{"label": "CPU 使用率", "reason": "CPU 偏高"}],
        [{"title": "连接数告警", "severity": "high"}],
    )

    assert any("性能" in item or "慢 SQL" in item for item in focus_areas)
    assert any("CPU 使用率" in item for item in focus_areas)
    assert any("连接数告警" in item for item in focus_areas)


def test_render_diagnostic_brief_contains_core_sections():
    brief = {
        "datasource": {"name": "prod-mysql", "db_type": "mysql", "host": "127.0.0.1", "port": 3306},
        "issue_category": "performance",
        "user_symptoms": ["数据库很慢"],
        "abnormal_signals": [{"severity": "high", "label": "CPU 使用率", "value": "92.0%", "reason": "CPU 偏高"}],
        "active_alerts": [{"severity": "high", "title": "CPU 告警", "status": "active"}],
        "focus_areas": ["先看整体负载与连接压力"],
        "recent_conclusion": {"summary": "历史上出现过慢 SQL 导致 CPU 飙高"},
        "recent_report": {"summary": "最近巡检提示缓存命中率下降"},
    }

    rendered = render_diagnostic_brief_for_prompt(brief)
    assert "System pre-diagnosis brief" in rendered
    assert "likely_issue_category: performance" in rendered
    assert "abnormal_signal" in rendered
    assert "latest_related_conclusion" in rendered


def test_build_diagnosis_event_payload_summarizes_tool_result():
    payload = _build_diagnosis_event_payload(
        "tool_result",
        {
            "tool_name": "get_db_status",
            "result": '{"cache_hit_rate": 91.2, "slow_queries": 8}',
            "execution_time_ms": 15,
            "tool_call_id": "call_1",
        },
    )

    assert payload["tool_name"] == "get_db_status"
    assert payload["execution_time_ms"] == 15
    assert payload["success"] is True
    assert "cache_hit_rate" in payload["summary"]
