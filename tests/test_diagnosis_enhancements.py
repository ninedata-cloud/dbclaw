from backend.agent.diagnosis_context import (
    build_focus_areas,
    extract_metric_signals,
    render_diagnostic_brief_for_prompt,
)
from backend.services.chat_orchestration_service import _build_diagnosis_event_payload
from backend.services.tool_visualization_service import build_tool_result_visualization


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


def test_build_tool_result_visualization_for_monitoring_history():
    visualization = build_tool_result_visualization(
        "query_monitoring_history",
        {
            "success": True,
            "datasource": {"id": 12, "name": "prod-mysql"},
            "host": {"id": 8, "name": "db-host-01", "host": "10.0.0.8"},
            "time_range": {
                "start_time": "2026-04-08T00:00:00",
                "end_time": "2026-04-08T02:00:00",
            },
            "aggregation": {"bucket_seconds": 900, "bucket_label": "15m", "max_points": 96},
            "datasource_metrics": {
                "selected_metric_names": ["cpu_usage", "qps"],
                "summary": {
                    "cpu_usage": {"avg": 32.4, "min": 21.0, "max": 61.3, "last": 28.5},
                    "qps": {"avg": 128.2, "min": 97.0, "max": 166.4, "last": 143.7},
                },
                "series": {
                    "cpu_usage": [
                        {"bucket_start": "2026-04-08T00:00:00", "avg": 25.1, "last": 25.1},
                        {"bucket_start": "2026-04-08T00:15:00", "avg": 28.5, "last": 28.5},
                    ],
                    "qps": [
                        {"bucket_start": "2026-04-08T00:00:00", "avg": 118.6, "last": 118.6},
                        {"bucket_start": "2026-04-08T00:15:00", "avg": 143.7, "last": 143.7},
                    ],
                },
            },
            "host_metrics": {
                "available": True,
                "selected_metric_names": ["memory_usage"],
                "summary": {
                    "memory_usage": {"avg": 68.4, "min": 60.0, "max": 72.1, "last": 70.8},
                },
                "series": {
                    "memory_usage": [
                        {"bucket_start": "2026-04-08T00:00:00", "avg": 66.2, "last": 66.2},
                        {"bucket_start": "2026-04-08T00:15:00", "avg": 70.8, "last": 70.8},
                    ],
                },
            },
        },
    )

    assert visualization is not None
    assert visualization["type"] == "monitoring_history"
    assert visualization["aggregation"]["bucket_label"] == "15m"
    assert len(visualization["panels"]) == 2
    assert visualization["panels"][0]["metrics"][0]["name"] == "cpu_usage"
    assert visualization["panels"][1]["metrics"][0]["summary"]["last"] == 70.8
    assert visualization["panels"][0]["metrics"][0]["points"][0]["avg"] == 25.1
    assert visualization["panels"][0]["metrics"][0]["points"][0]["min"] is None
    assert visualization["panels"][0]["metrics"][0]["points"][0]["last"] == 25.1


def test_build_tool_result_visualization_skips_failed_monitoring_history():
    visualization = build_tool_result_visualization(
        "query_monitoring_history",
        {"success": False, "error": "当前数据源未关联主机"},
    )

    assert visualization is None
