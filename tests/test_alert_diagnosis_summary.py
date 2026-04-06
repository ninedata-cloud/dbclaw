import pytest

from backend.services.alert_service import (
    _extract_diagnosis_parts,
    normalize_alert_diagnosis_fields,
)


def test_extract_diagnosis_parts_prefers_concise_root_cause_over_process_text():
    diagnosis_text = """
我来分析这个 CPU 使用率告警。

让我制定诊断计划：
1. 获取数据库层面的状态信息
2. 获取操作系统层面的 CPU 和进程信息

现在开始收集证据：让我获取更多的系统信息和数据库层面的详细信息。

## 告警摘要
多数据库实例竞争 CPU 资源，导致 vastbase 进程持续高占用。

## 根本原因
- 主机上同时运行多个数据库实例，共同争用 4 核 CPU 资源。
- vastbase 进程 CPU 占用持续在 80% 以上，系统负载 7.26，已超过主机承载能力。

## 处置建议
1. 优先排查并限制其他数据库实例的 CPU 消耗。
2. 检查 vastbase 当前高 CPU 会话和慢 SQL。
"""

    root_cause, recommended_actions, summary = _extract_diagnosis_parts(diagnosis_text)

    assert root_cause is not None
    assert "数据库实例" in root_cause
    assert "CPU" in root_cause
    assert "让我" not in root_cause

    assert recommended_actions is not None
    assert "优先排查并限制其他数据库实例的 CPU 消耗" in recommended_actions
    assert "让我" not in recommended_actions

    assert summary == "多数据库实例竞争 CPU 资源，导致 vastbase 进程持续高占用。"
    assert "让我" not in summary


def test_extract_diagnosis_parts_can_parse_unstructured_root_cause_sentence():
    diagnosis_text = """
现在我已经收集了足够的证据。
根据收集的数据分析，CPU 使用率告警的根本原因是多数据库实例竞争系统资源，而非单一数据库负载过高。
建议先限制非核心实例资源占用，再排查 vastbase 高 CPU 会话。
"""

    root_cause, recommended_actions, summary = _extract_diagnosis_parts(diagnosis_text)

    assert root_cause == "多数据库实例竞争系统资源，而非单一数据库负载过高"
    assert summary == "多数据库实例竞争系统资源，而非单一数据库负载过高"
    assert recommended_actions is not None
    assert "限制非核心实例资源占用" in recommended_actions


def test_normalize_alert_diagnosis_fields_compacts_legacy_summary():
    legacy_summary = """
我来分析这个 CPU 使用率告警。
让我制定诊断计划：
1. 获取数据库层面的状态信息
2. 获取操作系统层面的 CPU 和进程信息
"""

    normalized = normalize_alert_diagnosis_fields(
        root_cause="多数据库实例竞争系统资源，导致 CPU 持续过载。",
        recommended_actions="优先限制其他实例 CPU；检查 vastbase 高 CPU 会话。",
        summary=legacy_summary,
    )

    assert normalized["summary"] == "多数据库实例竞争系统资源，导致 CPU 持续过载。"
    assert normalized["root_cause"] == "多数据库实例竞争系统资源，导致 CPU 持续过载。"
    assert normalized["recommended_actions"] == "优先限制其他实例 CPU；检查 vastbase 高 CPU 会话。"
