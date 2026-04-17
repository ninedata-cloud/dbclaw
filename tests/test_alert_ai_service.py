from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.services.alert_ai_service import (
    AI_DECISION_ALERT,
    AI_DECISION_NO_ALERT,
    AI_DECISION_RECOVER,
    DEFAULT_ANALYSIS_CONFIG,
    INLINE_AI_POLICY_DISPLAY_NAME,
    AlertAIJudgeResult,
    AlertAIPolicyBinding,
    _compress_alert_ai_evidence,
    _compress_alert_ai_reason,
    _build_metric_features,
    _compile_policy_profile_locally,
    _normalize_judge_result,
    _resolve_sampling_interval_seconds,
    decide_alert_ai_candidate,
    normalize_analysis_config,
    compute_ai_transition,
    enforce_policy_severity_constraint,
    extract_policy_severity_instruction,
    normalize_alert_engine_mode,
    normalize_ai_policy_source,
    resolve_alert_ai_policy_binding,
    should_skip_candidate_due_to_interval,
)
from backend.routers.inspections import InspectionConfigSchema


def test_normalize_alert_engine_mode_and_policy_source():
    assert normalize_alert_engine_mode("ai") == "ai"
    assert normalize_alert_engine_mode("threshold") == "threshold"
    assert normalize_alert_engine_mode("weird") == "inherit"

    assert normalize_ai_policy_source("template") == "template"
    assert normalize_ai_policy_source("inline") == "inline"
    assert normalize_ai_policy_source("unknown") == "inline"


@pytest.mark.asyncio
async def test_inline_ai_policy_binding_uses_fixed_friendly_display_name():
    binding = await resolve_alert_ai_policy_binding(
        db=None,
        ai_policy_source="inline",
        ai_policy_text="请结合 CPU、磁盘使用率、活跃连接数及最近 15 分钟趋势判断是否异常",
        ai_policy_id=None,
        alert_ai_model_id=None,
    )

    assert binding is not None
    assert binding.display_name == INLINE_AI_POLICY_DISPLAY_NAME


def test_compute_ai_transition_requires_two_confident_alerts_before_trigger():
    current_time = datetime(2026, 4, 11, 10, 0, 0)

    first = compute_ai_transition(
        active=False,
        decision=AI_DECISION_ALERT,
        confidence=0.92,
        confidence_threshold=0.7,
        consecutive_alert_count=0,
        consecutive_recover_count=0,
        cooldown_until=None,
        current_time=current_time,
    )
    assert first.action == "noop"
    assert first.active is False
    assert first.consecutive_alert_count == 1

    second = compute_ai_transition(
        active=False,
        decision=AI_DECISION_ALERT,
        confidence=0.92,
        confidence_threshold=0.7,
        consecutive_alert_count=first.consecutive_alert_count,
        consecutive_recover_count=0,
        cooldown_until=None,
        current_time=current_time + timedelta(minutes=1),
    )
    assert second.action == "trigger_alert"
    assert second.active is True
    assert second.consecutive_alert_count == 0


def test_compute_ai_transition_requires_two_confident_recovers_before_close():
    current_time = datetime(2026, 4, 11, 10, 0, 0)

    first = compute_ai_transition(
        active=True,
        decision=AI_DECISION_RECOVER,
        confidence=0.88,
        confidence_threshold=0.7,
        consecutive_alert_count=0,
        consecutive_recover_count=0,
        cooldown_until=None,
        current_time=current_time,
    )
    assert first.action == "noop"
    assert first.active is True
    assert first.consecutive_recover_count == 1

    second = compute_ai_transition(
        active=True,
        decision=AI_DECISION_RECOVER,
        confidence=0.88,
        confidence_threshold=0.7,
        consecutive_alert_count=0,
        consecutive_recover_count=first.consecutive_recover_count,
        cooldown_until=None,
        current_time=current_time + timedelta(minutes=1),
    )
    assert second.action == "recover_alert"
    assert second.active is False
    assert second.cooldown_until is not None


def test_compute_ai_transition_respects_cooldown():
    current_time = datetime(2026, 4, 11, 10, 0, 0)
    transition = compute_ai_transition(
        active=False,
        decision=AI_DECISION_ALERT,
        confidence=0.99,
        confidence_threshold=0.7,
        consecutive_alert_count=1,
        consecutive_recover_count=0,
        cooldown_until=current_time + timedelta(minutes=5),
        current_time=current_time,
    )
    assert transition.action == "noop"
    assert transition.active is False
    assert transition.consecutive_alert_count == 0


def test_normalize_judge_result_clamps_and_defaults():
    parsed = {
        "decision": "alert",
        "severity": "high",
        "confidence": 1.2,
        "reason": "CPU 与连接数同时升高",
        "evidence": ["cpu_usage 95", "connections_active 320"],
        "trigger_inspection": True,
    }
    result = _normalize_judge_result(parsed, raw_response='{"ok":true}')
    assert result.decision == "alert"
    assert result.severity == "high"
    assert result.confidence == 1.0
    assert result.trigger_inspection is True
    assert len(result.evidence) == 2


def test_normalize_judge_result_rejects_invalid_or_missing_severity():
    with pytest.raises(ValueError, match="缺少 severity"):
        _normalize_judge_result(
            {
                "decision": "alert",
                "confidence": 0.8,
                "reason": "命中规则",
                "evidence": [],
                "trigger_inspection": False,
            },
            raw_response='{"ok":true}',
        )

    with pytest.raises(ValueError, match="非法 severity"):
        _normalize_judge_result(
            {
                "decision": "alert",
                "severity": "urgent",
                "confidence": 0.8,
                "reason": "命中规则",
                "evidence": [],
                "trigger_inspection": False,
            },
            raw_response='{"ok":true}',
        )


def test_extract_policy_severity_instruction_supports_cn_en_and_priority_aliases():
    assert extract_policy_severity_instruction("触发严重告警")[0] == "critical"
    assert extract_policy_severity_instruction("critical 告警")[0] == "critical"
    assert extract_policy_severity_instruction("按高优先级告警")[0] == "high"
    assert extract_policy_severity_instruction("P2 告警")[0] == "high"
    assert extract_policy_severity_instruction("中优先级告警")[0] == "medium"
    assert extract_policy_severity_instruction("low 告警")[0] == "low"


def test_extract_policy_severity_instruction_ignores_range_expressions():
    severity, source, warning = extract_policy_severity_instruction("至少高告警，必要时提高等级")
    assert severity is None
    assert source == "inferred"
    assert warning is not None


def test_enforce_policy_severity_constraint_marks_conflict_invalid():
    binding = AlertAIPolicyBinding(
        policy_id=1,
        policy_source="template",
        rule_text="如果命中则触发高优先级告警",
        model_id=2,
        policy_fingerprint="fp",
        display_name="高优先级模板",
        policy_severity_hint="high",
        severity_constraint_mode="explicit",
        severity_warning=None,
    )
    judge_result = AlertAIJudgeResult(
        decision="alert",
        severity="critical",
        confidence=0.92,
        reason="模型判断非常严重",
        evidence=["cpu_usage 98"],
        trigger_inspection=True,
        raw_response="{}",
    )

    constrained = enforce_policy_severity_constraint(judge_result, binding)
    assert constrained.error_message is not None
    assert constrained.severity_source == "invalid"
    assert "不一致" in constrained.error_message


def test_enforce_policy_severity_constraint_marks_matching_explicit():
    binding = AlertAIPolicyBinding(
        policy_id=1,
        policy_source="template",
        rule_text="如果命中则触发高优先级告警",
        model_id=2,
        policy_fingerprint="fp",
        display_name="高优先级模板",
        policy_severity_hint="high",
        severity_constraint_mode="explicit",
        severity_warning=None,
    )
    judge_result = AlertAIJudgeResult(
        decision="alert",
        severity="high",
        confidence=0.92,
        reason="模型判断为高等级",
        evidence=["cpu_usage 91"],
        trigger_inspection=True,
        raw_response="{}",
    )

    constrained = enforce_policy_severity_constraint(judge_result, binding)
    assert constrained.error_message is None
    assert constrained.severity_source == "explicit"


def test_compress_alert_ai_reason_removes_meta_and_duplication():
    reason = (
        "模板中存在多个明确等级表达，已按 AI 自主判断处理；"
        "CPU当前值91.0%超过严重阈值90%；"
        "recent_samples显示CPU波动剧烈，07:25:37达89.2%后回落至12.7%，07:29:37再次升至91.0%；"
        "采样间隔60秒，精度限制无法精确判断30秒持续条件；"
        "CPU当前值91.0%超过严重阈值90%"
    )

    compact = _compress_alert_ai_reason(
        decision=AI_DECISION_ALERT,
        severity="critical",
        reason=reason,
    )

    assert "模板中存在多个明确等级表达" not in compact
    assert "recent_samples" not in compact
    assert "精度限制" not in compact
    assert "CPU" in compact
    assert "告警" in compact
    assert len(compact) <= 48


def test_compress_alert_ai_evidence_limits_count_and_length():
    evidence = [
        "CPU当前值91.0%超过严重阈值90%",
        "采样间隔60秒，精度限制无法精确判断30秒持续条件",
        "CPU当前值91.0%超过严重阈值90%",
        "中等条件80%持续60秒未满足",
    ]

    compact = _compress_alert_ai_evidence(evidence)

    assert len(compact) <= 2
    assert all(len(item) <= 24 for item in compact)
    assert all("精度限制" not in item for item in compact)


def test_build_metric_features_includes_recent_samples_for_duration_judgement():
    collected_at = datetime(2026, 4, 11, 18, 39, 17)
    snapshots_desc = [
        SimpleNamespace(collected_at=collected_at, data={"cpu_usage": 28.0}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=60), data={"cpu_usage": 24.1}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=120), data={"cpu_usage": 10.6}),
    ]

    features = _build_metric_features(
        snapshots_desc,
        current_metrics={"cpu_usage": 28.0},
        metric_names=["cpu_usage"],
        collected_at=collected_at,
    )

    cpu_feature = features["cpu_usage"]
    assert cpu_feature["recent_sample_count"] == 3
    assert cpu_feature["recent_samples_span_seconds"] == 120
    assert cpu_feature["recent_samples"] == [
        {"collected_at": (collected_at - timedelta(seconds=120)).isoformat(), "value": 10.6},
        {"collected_at": (collected_at - timedelta(seconds=60)).isoformat(), "value": 24.1},
        {"collected_at": collected_at.isoformat(), "value": 28.0},
    ]


def test_resolve_sampling_interval_seconds_prefers_global_config():
    snapshots_desc = [
        SimpleNamespace(collected_at=datetime(2026, 4, 11, 18, 39, 17), data={}),
        SimpleNamespace(collected_at=datetime(2026, 4, 11, 18, 38, 17), data={}),
    ]

    assert _resolve_sampling_interval_seconds(snapshots_desc, 45) == 45


def test_resolve_sampling_interval_seconds_falls_back_to_snapshot_gap():
    snapshots_desc = [
        SimpleNamespace(collected_at=datetime(2026, 4, 11, 18, 39, 17), data={}),
        SimpleNamespace(collected_at=datetime(2026, 4, 11, 18, 38, 7), data={}),
        SimpleNamespace(collected_at=datetime(2026, 4, 11, 18, 36, 57), data={}),
    ]

    assert _resolve_sampling_interval_seconds(snapshots_desc, None) == 70


def test_compile_policy_profile_locally_extracts_trigger_and_recovery_profiles():
    profile, complete, error = _compile_policy_profile_locally(
        "严重：cpu 超过90%，持续3秒\n中告警：cpu 超过80%，持续10秒\n低告警：cpu 超过20%，持续60秒"
    )

    assert complete is True
    assert error is None
    assert profile["focus_metrics"] == ["cpu_usage"]
    assert len(profile["trigger_conditions"]) == 3
    assert profile["trigger_conditions"][-1]["severity"] == "critical"
    assert profile["fallback_mode"] == "threshold_rules"
    assert profile["recovery_conditions"][0]["metric"] == "cpu_usage"
    assert profile["recovery_conditions"][0]["operator"] == "<="
    assert profile["recovery_conditions"][0]["threshold"] == 20.0


def test_compile_policy_profile_locally_keeps_all_focus_metrics_for_natural_language_policy():
    profile, complete, error = _compile_policy_profile_locally(
        "请结合 CPU、磁盘使用率、活跃连接数及最近 15 分钟趋势判断该实例是否处于明显异常状态。"
        "只有在异常持续、影响扩大或风险较高时才触发告警；若只是短时抖动或接近阈值但证据不足，则不触发告警。"
    )

    assert complete is False
    assert error is not None
    assert profile["focus_metrics"] == ["cpu_usage", "disk_usage", "connections_active"]
    assert profile["trigger_conditions"] == []
    assert profile["fallback_mode"] == "threshold_rules"


def test_decide_alert_ai_candidate_uses_near_threshold_rising_signal():
    collected_at = datetime(2026, 4, 11, 18, 39, 17)
    snapshots_desc = [
        SimpleNamespace(collected_at=collected_at, data={"cpu_usage": 72.0}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=60), data={"cpu_usage": 68.0}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=120), data={"cpu_usage": 60.0}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=900), data={"cpu_usage": 45.0}),
    ]
    binding = AlertAIPolicyBinding(
        policy_id=1,
        policy_source="template",
        rule_text="高告警：cpu 超过80%，持续60秒",
        model_id=None,
        policy_fingerprint="fp",
        display_name="test",
        analysis_config=normalize_analysis_config(None),
        compiled_trigger_profile={
            "focus_metrics": ["cpu_usage"],
            "trigger_conditions": [
                {"metric": "cpu_usage", "operator": ">", "threshold": 80, "duration_seconds": 60, "severity": "high"}
            ],
            "recovery_conditions": [],
            "escalation_rules": [],
            "fallback_mode": "threshold_rules",
        },
    )
    state = SimpleNamespace(active=False, last_ai_evaluated_at=None)

    gate_decision, _metric_features = decide_alert_ai_candidate(
        binding=binding,
        state=state,
        current_metrics={"cpu_usage": 72.0},
        collected_at=collected_at,
        snapshots_desc=snapshots_desc,
        threshold_rules=None,
        current_alert_severity=None,
        sampling_interval_seconds=60,
    )

    assert gate_decision.should_evaluate is True
    assert gate_decision.candidate_type == "near_threshold"


def test_decide_alert_ai_candidate_supports_recovery_for_active_alert():
    collected_at = datetime(2026, 4, 11, 18, 39, 17)
    snapshots_desc = [
        SimpleNamespace(collected_at=collected_at, data={"cpu_usage": 15.0}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=60), data={"cpu_usage": 18.0}),
        SimpleNamespace(collected_at=collected_at - timedelta(seconds=120), data={"cpu_usage": 19.0}),
    ]
    binding = AlertAIPolicyBinding(
        policy_id=1,
        policy_source="template",
        rule_text="低告警：cpu 超过20%，持续60秒",
        model_id=None,
        policy_fingerprint="fp",
        display_name="test",
        analysis_config=normalize_analysis_config({"min_recovery_consecutive_samples": 2}),
        compiled_trigger_profile={
            "focus_metrics": ["cpu_usage"],
            "trigger_conditions": [{"metric": "cpu_usage", "operator": ">", "threshold": 20, "duration_seconds": 60, "severity": "low"}],
            "recovery_conditions": [{"metric": "cpu_usage", "operator": "<=", "threshold": 20, "duration_seconds": 120}],
            "escalation_rules": [],
            "fallback_mode": "threshold_rules",
        },
    )
    state = SimpleNamespace(active=True, last_ai_evaluated_at=collected_at - timedelta(minutes=20))

    gate_decision, _metric_features = decide_alert_ai_candidate(
        binding=binding,
        state=state,
        current_metrics={"cpu_usage": 15.0},
        collected_at=collected_at,
        snapshots_desc=snapshots_desc,
        threshold_rules=None,
        current_alert_severity="low",
        sampling_interval_seconds=60,
    )

    assert gate_decision.should_evaluate is True
    assert gate_decision.candidate_type == "recovery"


def test_should_skip_candidate_due_to_interval_for_same_fingerprint():
    current_time = datetime(2026, 4, 11, 18, 39, 17)
    state = SimpleNamespace(
        last_candidate_fingerprint="same",
        last_ai_evaluated_at=current_time - timedelta(seconds=30),
    )
    gate_decision = SimpleNamespace(candidate_type="trigger", fingerprint="same")

    should_skip, reason = should_skip_candidate_due_to_interval(
        state,
        gate_decision,
        DEFAULT_ANALYSIS_CONFIG,
        current_time,
    )

    assert should_skip is True
    assert reason == "same_candidate_throttled"


def test_inspection_config_schema_allows_threshold_only_payload():
    config = InspectionConfigSchema(
        enabled=True,
        schedule_interval=3600,
        use_ai_analysis=True,
        threshold_rules={"cpu_usage": {"threshold": 80, "duration": 60}},
    )
    assert config.alert_engine_mode == "inherit"
    assert config.ai_policy_source == "inline"


def test_inspection_config_schema_requires_ai_rule_in_ai_mode():
    with pytest.raises(ValueError):
        InspectionConfigSchema(
            enabled=True,
            schedule_interval=3600,
            use_ai_analysis=True,
            alert_engine_mode="ai",
            ai_policy_source="inline",
            threshold_rules={},
        )

    with pytest.raises(ValueError):
        InspectionConfigSchema(
            enabled=True,
            schedule_interval=3600,
            use_ai_analysis=True,
            alert_engine_mode="ai",
            ai_policy_source="template",
            threshold_rules={},
        )

    config = InspectionConfigSchema(
        enabled=True,
        schedule_interval=3600,
        use_ai_analysis=True,
        alert_engine_mode="ai",
        ai_policy_source="template",
        ai_policy_id=3,
        threshold_rules={},
    )
    assert config.ai_policy_id == 3
