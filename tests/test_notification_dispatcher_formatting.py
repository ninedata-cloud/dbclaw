from backend.services.notification_dispatcher import (
    _format_diagnosis_markdown,
    _render_notification_metric_summary,
)


def test_format_diagnosis_markdown_splits_semicolon_text_into_bullets():
    text = "持续观察即可；排查 I/O Wait 偏高根因；调优告警阈值"
    formatted = _format_diagnosis_markdown(text)

    assert formatted == (
        "- 持续观察即可\n"
        "- 排查 I/O Wait 偏高根因\n"
        "- 调优告警阈值"
    )


def test_render_notification_metric_summary_prefers_native_metric_values():
    raw_metrics = {
        "cpu_usage": 38.3,
        "disk_usage": 51,
        "connections_active": 1,
    }

    rendered = _render_notification_metric_summary(
        raw_metrics,
        ["cpu_usage", "disk_usage", "connections_active"],
    )

    assert rendered == (
        "- CPU 使用率：38.3%\n"
        "- 磁盘使用率：51.0%\n"
        "- 活跃连接数：1"
    )
