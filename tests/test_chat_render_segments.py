import json

from backend.services.chat_orchestration_service import apply_render_segments_event


def test_render_segments_keep_content_tool_content_order():
    segments = []
    segments = apply_render_segments_event(segments, {
        "type": "content",
        "content": "先检查连接。\n",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_call",
        "tool_name": "mysql_get_db_status",
        "tool_args": {"connection_id": 1},
        "tool_call_id": "call_1",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_result",
        "tool_name": "mysql_get_db_status",
        "tool_call_id": "call_1",
        "result": json.dumps({"success": True, "connections": 23}),
        "execution_time_ms": 128,
        "skill_execution_id": 7,
    })
    segments = apply_render_segments_event(segments, {
        "type": "content",
        "content": "连接数正常，但负载偏高。\n",
    })

    assert [segment["type"] for segment in segments] == ["markdown", "tool", "markdown"]
    assert segments[0]["content"] == "先检查连接。\n"
    assert segments[1]["tool_call_id"] == "call_1"
    assert segments[1]["status"] == "completed"
    assert segments[1]["execution_time_ms"] == 128
    assert segments[1]["metadata"]["skill_execution_id"] == 7
    assert "connections=23" in segments[1]["summary"]
    assert segments[2]["content"] == "连接数正常，但负载偏高。\n"


def test_render_segments_support_multiple_tools_without_reordering():
    segments = []
    segments = apply_render_segments_event(segments, {
        "type": "content",
        "content": "开始排查。\n",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_call",
        "tool_name": "mysql_get_db_status",
        "tool_args": {"connection_id": 1},
        "tool_call_id": "call_1",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_result",
        "tool_name": "mysql_get_db_status",
        "tool_call_id": "call_1",
        "result": json.dumps({"success": True, "connections": 23}),
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_call",
        "tool_name": "mysql_get_slow_queries",
        "tool_args": {"connection_id": 1},
        "tool_call_id": "call_2",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_result",
        "tool_name": "mysql_get_slow_queries",
        "tool_call_id": "call_2",
        "result": json.dumps({"success": True, "rows": [1, 2, 3]}),
    })

    assert [segment["tool_call_id"] for segment in segments if segment["type"] == "tool"] == ["call_1", "call_2"]
    assert segments[1]["tool_name"] == "mysql_get_db_status"
    assert segments[2]["tool_name"] == "mysql_get_slow_queries"


def test_approval_request_creates_waiting_tool_and_tool_call_reuses_same_segment():
    segments = []
    segments = apply_render_segments_event(segments, {
        "type": "approval_request",
        "approval_id": "approval_1",
        "tool_name": "execute_any_sql",
        "tool_args": {"sql": "DELETE FROM t"},
        "tool_call_id": "call_approval",
        "summary": "技能 execute_any_sql 需要确认后再执行。",
        "risk_level": "high",
        "risk_reason": "该 SQL 可能修改数据库状态，需要确认后再执行。",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_call",
        "tool_name": "execute_any_sql",
        "tool_args": {"sql": "DELETE FROM t"},
        "tool_call_id": "call_approval",
    })

    assert len(segments) == 1
    assert segments[0]["type"] == "tool"
    assert segments[0]["tool_call_id"] == "call_approval"
    assert segments[0]["status"] == "running"
    assert segments[0]["summary"] == "已发起调用，等待返回结果"
    assert segments[0]["args"]["sql"] == "DELETE FROM t"
    assert segments[0]["metadata"]["approval_id"] == "approval_1"
    assert segments[0]["metadata"]["approval_status"] == "pending"
    assert segments[0]["metadata"]["risk_reason"] == "该 SQL 可能修改数据库状态，需要确认后再执行。"


def test_failed_tool_result_marks_segment_failed():
    segments = []
    segments = apply_render_segments_event(segments, {
        "type": "tool_call",
        "tool_name": "mysql_get_db_status",
        "tool_args": {"connection_id": 1},
        "tool_call_id": "call_fail",
    })
    segments = apply_render_segments_event(segments, {
        "type": "tool_result",
        "tool_name": "mysql_get_db_status",
        "tool_call_id": "call_fail",
        "result": json.dumps({"success": False, "error": "no_host_configured"}),
    })

    assert segments[0]["status"] == "failed"
    assert "no_host_configured" in segments[0]["summary"]
