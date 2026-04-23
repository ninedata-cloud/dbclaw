from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any, Iterable, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.ai_model import AIModel
from backend.models.alert_ai_evaluation_log import AlertAIEvaluationLog
from backend.models.alert_ai_policy import AlertAIPolicy
from backend.models.alert_ai_runtime_state import AlertAIRuntimeState
from backend.models.alert_message import AlertMessage
from backend.models.datasource_metric import DatasourceMetric
from backend.services.ai_agent import get_ai_client, request_text_response_with_usage
from backend.services.alert_service import AlertService
from backend.services.config_service import get_config
from backend.utils.datetime_helper import now
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)

DEFAULT_ALERT_ENGINE_MODE = "threshold"
DEFAULT_AI_POLICY_SOURCE = "inline"
AI_DECISION_ALERT = "alert"
AI_DECISION_NO_ALERT = "no_alert"
AI_DECISION_RECOVER = "recover"
AI_ALLOWED_DECISIONS = {AI_DECISION_ALERT, AI_DECISION_NO_ALERT, AI_DECISION_RECOVER}
AI_ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
SEVERITY_SOURCE_EXPLICIT = "explicit"
SEVERITY_SOURCE_INFERRED = "inferred"
SEVERITY_SOURCE_INVALID = "invalid"
DEFAULT_AI_ALERT_TIMEOUT_SECONDS = 3
DEFAULT_AI_ALERT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_AI_ALERT_COOLDOWN_SECONDS = 900
DEFAULT_REQUIRED_CONFIRMATIONS = 2
MAX_HISTORY_SNAPSHOTS = 1440
MAX_FEATURE_METRICS = 8
MAX_RECENT_SAMPLES_PER_METRIC = 8
DEFAULT_ANALYSIS_STRATEGY = "candidate_only"
INLINE_AI_POLICY_DISPLAY_NAME = "AI 智能判警"
DEFAULT_ANALYSIS_CONFIG = {
    "inactive_min_eval_interval_seconds": 300,
    "active_recovery_min_eval_interval_seconds": 180,
    "active_backstop_eval_seconds": 1800,
    "near_threshold_ratio": 0.9,
    "trend_window_samples": 5,
    "min_recovery_consecutive_samples": 2,
}
SEVERITY_RANKS = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
SEVERITY_LABELS = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _json_dumps(payload: Any, *, sort_keys: bool = False) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
        default=_json_default,
    )

PREFERRED_METRICS = [
    "cpu_usage",
    "memory_usage",
    "disk_usage",
    "connections_active",
    "connections_total",
    "connections_waiting",
    "qps",
    "tps",
    "iops",
    "throughput",
    "cache_hit_rate",
    "lock_waiting",
    "longest_transaction_sec",
]

METRIC_ALIASES: dict[str, list[str]] = {
    "cpu_usage": ["cpu_usage", "cpu_usage_percent", "cpu_percent"],
    "memory_usage": ["memory_usage", "memory_usage_percent", "mem_percent"],
    "disk_usage": ["disk_usage", "disk_usage_percent", "disk_percent"],
    "connections_active": ["connections_active", "threads_running", "active_connections", "connection_count"],
    "connections_total": ["connections_total", "threads_connected", "total_connections"],
    "connections_waiting": ["connections_waiting", "lock_waiting_connections", "waiting_connections"],
    "qps": ["qps", "questions_per_second"],
    "tps": ["tps", "transactions_per_second"],
    "iops": ["iops"],
    "throughput": ["throughput"],
    "cache_hit_rate": ["cache_hit_rate", "buffer_pool_hit_rate"],
    "lock_waiting": ["lock_waiting", "lock_waits"],
    "longest_transaction_sec": ["longest_transaction_sec"],
}

METRIC_KEYWORDS: dict[str, list[str]] = {
    "cpu_usage": ["cpu", "cpu使用率", "cpu usage"],
    "memory_usage": ["内存", "memory", "mem"],
    "disk_usage": ["磁盘", "disk", "磁盘使用率"],
    "connections_active": ["连接数", "活跃连接", "active connections", "connections"],
    "connections_total": ["总连接", "连接总数"],
    "connections_waiting": ["等待连接", "阻塞连接", "waiting connections"],
    "qps": ["qps", "每秒查询", "queries per second"],
    "tps": ["tps", "每秒事务", "transactions per second"],
    "iops": ["iops"],
    "throughput": ["吞吐", "throughput"],
    "cache_hit_rate": ["缓存命中率", "cache hit"],
    "lock_waiting": ["锁等待", "lock wait"],
    "longest_transaction_sec": ["长事务", "事务时长", "transaction"],
}

SEVERITY_EXPLICIT_PATTERNS: list[tuple[str, tuple[re.Pattern[str], ...]]] = [
    (
        "critical",
        (
            re.compile(r"\bcritical\b", re.IGNORECASE),
            re.compile(r"\bp1\b", re.IGNORECASE),
            re.compile(r"(?:触发|按|为|设为|级别为|严重程度为)?\s*严重(?:告警|级别|优先级)?"),
            re.compile(r"(?:触发|按|为|设为)?\s*紧急(?:告警|级别|优先级)?"),
        ),
    ),
    (
        "high",
        (
            re.compile(r"\bhigh\b", re.IGNORECASE),
            re.compile(r"\bp2\b", re.IGNORECASE),
            re.compile(r"(?:触发|按|为|设为|级别为|严重程度为)?\s*高(?:告警|级别)?"),
            re.compile(r"(?:触发|按|为|设为)?\s*高优先级"),
        ),
    ),
    (
        "medium",
        (
            re.compile(r"\bmedium\b", re.IGNORECASE),
            re.compile(r"\bp3\b", re.IGNORECASE),
            re.compile(r"(?:触发|按|为|设为|级别为|严重程度为)?\s*中(?:告警|级别)?"),
            re.compile(r"(?:触发|按|为|设为)?\s*中优先级"),
        ),
    ),
    (
        "low",
        (
            re.compile(r"\blow\b", re.IGNORECASE),
            re.compile(r"\bp4\b", re.IGNORECASE),
            re.compile(r"(?:触发|按|为|设为|级别为|严重程度为)?\s*低(?:告警|级别)?"),
            re.compile(r"(?:触发|按|为|设为)?\s*低优先级"),
            re.compile(r"(?:触发|按|为|设为)?\s*提示性(?:告警|级别)?"),
        ),
    ),
]

SEVERITY_RANGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"至少\s*(?:严重|紧急|高|中|低|critical|high|medium|low|p[1-4])", re.IGNORECASE),
    re.compile(r"不低于\s*(?:严重|紧急|高|中|低|critical|high|medium|low|p[1-4])", re.IGNORECASE),
    re.compile(r"最高\s*(?:严重|紧急|高|中|低|critical|high|medium|low|p[1-4])", re.IGNORECASE),
    re.compile(r"可适当提高等级", re.IGNORECASE),
    re.compile(r"根据情况(?:调整|提高|降低)等级", re.IGNORECASE),
)


@dataclass
class AlertAIPolicyBinding:
    policy_id: Optional[int]
    policy_source: str
    rule_text: str
    model_id: Optional[int]
    policy_fingerprint: str
    display_name: str
    policy_severity_hint: Optional[str] = None
    severity_constraint_mode: str = "inferred"
    severity_warning: Optional[str] = None
    analysis_strategy: str = DEFAULT_ANALYSIS_STRATEGY
    analysis_config: dict[str, Any] | None = None
    compiled_trigger_profile: dict[str, Any] | None = None
    compile_status: str = "pending"
    compile_error: Optional[str] = None
    compiled_at: Optional[datetime] = None


@dataclass
class AlertAIJudgeResult:
    decision: str
    severity: str
    confidence: float
    reason: str
    evidence: list[str]
    trigger_inspection: bool
    raw_response: str
    severity_source: str = SEVERITY_SOURCE_INFERRED
    policy_severity_hint: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    error_message: Optional[str] = None


@dataclass
class AlertAITransition:
    action: str  # noop, trigger_alert, recover_alert
    active: bool
    consecutive_alert_count: int
    consecutive_recover_count: int
    cooldown_until: Optional[datetime]


@dataclass
class AlertAIGateDecision:
    should_evaluate: bool
    candidate_type: str
    fingerprint: Optional[str]
    severity_hint: Optional[str]
    reason: str
    gate_reason: str
    matched_conditions: list[dict[str, Any]]
    gate_metrics: dict[str, Any]


def normalize_alert_engine_mode(mode: Optional[str]) -> str:
    normalized = (mode or "").strip().lower()
    if normalized in {"threshold", "ai", "inherit"}:
        return normalized
    return "inherit"


def normalize_ai_policy_source(source: Optional[str]) -> str:
    normalized = (source or "").strip().lower()
    if normalized in {"inline", "template"}:
        return normalized
    return DEFAULT_AI_POLICY_SOURCE


def normalize_analysis_strategy(strategy: Optional[str]) -> str:
    normalized = (strategy or "").strip().lower()
    return normalized if normalized == DEFAULT_ANALYSIS_STRATEGY else DEFAULT_ANALYSIS_STRATEGY


def normalize_analysis_config(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(DEFAULT_ANALYSIS_CONFIG)
    if not isinstance(config, dict):
        return merged

    int_fields = {
        "inactive_min_eval_interval_seconds",
        "active_recovery_min_eval_interval_seconds",
        "active_backstop_eval_seconds",
        "trend_window_samples",
        "min_recovery_consecutive_samples",
    }
    float_fields = {"near_threshold_ratio"}

    for key, value in config.items():
        if key in int_fields:
            try:
                merged[key] = max(1, int(value))
            except (TypeError, ValueError):
                continue
        elif key in float_fields:
            try:
                merged[key] = max(0.1, min(float(value), 1.5))
            except (TypeError, ValueError):
                continue

    return merged


async def get_default_alert_engine_mode(db: AsyncSession) -> str:
    default_mode = await get_config(db, "default_alert_engine_mode", default=DEFAULT_ALERT_ENGINE_MODE)
    normalized = (str(default_mode or DEFAULT_ALERT_ENGINE_MODE)).strip().lower()
    return normalized if normalized in {"threshold", "ai"} else DEFAULT_ALERT_ENGINE_MODE


async def resolve_effective_alert_engine_mode(db: AsyncSession, config) -> str:
    mode = normalize_alert_engine_mode(getattr(config, "alert_engine_mode", None))
    if mode == "inherit":
        return await get_default_alert_engine_mode(db)
    return mode


async def get_ai_alert_timeout_seconds(db: AsyncSession) -> int:
    timeout = await get_config(db, "ai_alert_timeout_seconds", default=DEFAULT_AI_ALERT_TIMEOUT_SECONDS)
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        return DEFAULT_AI_ALERT_TIMEOUT_SECONDS
    return max(1, min(value, 30))


async def get_ai_alert_confidence_threshold(db: AsyncSession) -> float:
    threshold = await get_config(
        db,
        "ai_alert_confidence_threshold",
        default=DEFAULT_AI_ALERT_CONFIDENCE_THRESHOLD,
    )
    try:
        value = float(threshold)
    except (TypeError, ValueError):
        return DEFAULT_AI_ALERT_CONFIDENCE_THRESHOLD
    return max(0.0, min(value, 1.0))


def compute_ai_transition(
    *,
    active: bool,
    decision: str,
    confidence: float,
    confidence_threshold: float,
    consecutive_alert_count: int,
    consecutive_recover_count: int,
    cooldown_until: Optional[datetime],
    current_time: datetime,
    required_confirmations: int = DEFAULT_REQUIRED_CONFIRMATIONS,
    cooldown_seconds: int = DEFAULT_AI_ALERT_COOLDOWN_SECONDS,
) -> AlertAITransition:
    decision = (decision or AI_DECISION_NO_ALERT).strip().lower()
    is_confident = confidence >= confidence_threshold

    if decision == AI_DECISION_ALERT and is_confident:
        if active:
            return AlertAITransition(
                action="noop",
                active=True,
                consecutive_alert_count=0,
                consecutive_recover_count=0,
                cooldown_until=cooldown_until,
            )
        if cooldown_until and current_time < cooldown_until:
            return AlertAITransition(
                action="noop",
                active=False,
                consecutive_alert_count=0,
                consecutive_recover_count=0,
                cooldown_until=cooldown_until,
            )

        next_alert_count = consecutive_alert_count + 1
        if next_alert_count >= required_confirmations:
            return AlertAITransition(
                action="trigger_alert",
                active=True,
                consecutive_alert_count=0,
                consecutive_recover_count=0,
                cooldown_until=cooldown_until,
            )
        return AlertAITransition(
            action="noop",
            active=False,
            consecutive_alert_count=next_alert_count,
            consecutive_recover_count=0,
            cooldown_until=cooldown_until,
        )

    if decision == AI_DECISION_RECOVER and is_confident:
        if not active:
            return AlertAITransition(
                action="noop",
                active=False,
                consecutive_alert_count=0,
                consecutive_recover_count=0,
                cooldown_until=cooldown_until,
            )

        next_recover_count = consecutive_recover_count + 1
        if next_recover_count >= required_confirmations:
            return AlertAITransition(
                action="recover_alert",
                active=False,
                consecutive_alert_count=0,
                consecutive_recover_count=0,
                cooldown_until=current_time + timedelta(seconds=cooldown_seconds),
            )
        return AlertAITransition(
            action="noop",
            active=True,
            consecutive_alert_count=0,
            consecutive_recover_count=next_recover_count,
            cooldown_until=cooldown_until,
        )

    return AlertAITransition(
        action="noop",
        active=active,
        consecutive_alert_count=0,
        consecutive_recover_count=0,
        cooldown_until=cooldown_until,
    )


def _extract_metric_value(metrics: dict[str, Any], metric_name: str) -> Optional[float]:
    candidates = METRIC_ALIASES.get(metric_name, [metric_name])
    for candidate in candidates:
        value = metrics.get(candidate)
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            stripped = value.strip()
            if stripped.endswith("%"):
                stripped = stripped[:-1]
            return float(stripped)
        except ValueError:
            return None
    return None


def _truncate_text(text: str, *, max_chars: int) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip(" ，,；;。") + "…"


def _normalize_reason_clause_for_dedup(text: str) -> str:
    normalized = re.sub(r"\d{1,2}:\d{2}:\d{2}", "", text or "")
    normalized = re.sub(r"\d+(?:\.\d+)?", "#", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip("；;，,。")


def _split_reason_clauses(text: str) -> list[str]:
    raw = re.sub(r"[\r\n]+", "；", text or "")
    return [item.strip("；;，,。 ") for item in re.split(r"[；;。]+", raw) if item.strip("；;，,。 ")]


def _clean_reason_clause(text: str) -> str:
    clause = (text or "").strip()
    clause = clause.replace("recent_samples显示", "")
    clause = clause.replace("recent_samples", "")
    clause = clause.replace("当前值", " ")
    clause = re.sub(r"\s+", " ", clause)
    clause = re.sub(r"\s*([%><=~～])\s*", r"\1", clause)
    clause = re.sub(r"\s+", " ", clause)
    return clause.strip("；;，,。 ")


def _is_meta_reason_clause(text: str) -> bool:
    clause = (text or "").strip()
    if not clause:
        return True
    meta_patterns = (
        r"模板中存在多个明确等级表达",
        r"已按 AI 自主判断处理",
        r"采样间隔.*精度限制",
        r"精度限制.*无法",
        r"鉴于采样间隔",
    )
    return any(re.search(pattern, clause, re.IGNORECASE) for pattern in meta_patterns)


def _score_reason_clause(text: str) -> int:
    clause = (text or "").strip()
    score = 0
    if re.search(r"(触发|告警|恢复|回落|暂不告警|未恢复|已恢复)", clause):
        score += 5
    if re.search(r"(超过|达到|低于|高于|回落至|触及|命中)", clause):
        score += 4
    if re.search(r"(严重阈值|高阈值|中阈值|低阈值|阈值)", clause):
        score += 4
    if re.search(r"(CPU|磁盘|连接|内存|QPS|TPS|复制|延迟|锁)", clause, re.IGNORECASE):
        score += 3
    if re.search(r"(波动|持续|阈值)", clause):
        score += 2
    if re.search(r"\d{1,2}:\d{2}:\d{2}", clause):
        score -= 4
    if re.search(r"(波动剧烈|再次升至|中间有多次)", clause):
        score -= 3
    if _is_meta_reason_clause(clause):
        score -= 8
    if len(clause) > 36:
        score -= 2
    return score


def _compress_alert_ai_reason(
    *,
    decision: str,
    severity: str,
    reason: str,
) -> str:
    clauses = []
    seen: set[str] = set()
    for raw_clause in _split_reason_clauses(reason):
        clause = _clean_reason_clause(raw_clause)
        if not clause or _is_meta_reason_clause(clause):
            continue
        dedup_key = _normalize_reason_clause_for_dedup(clause)
        if not dedup_key or dedup_key in seen:
            continue
        seen.add(dedup_key)
        clauses.append(clause)

    if not clauses:
        fallback = _truncate_text(reason or "", max_chars=36)
        if fallback:
            return fallback
        if decision == AI_DECISION_RECOVER:
            return "指标恢复正常，判定恢复"
        if decision == AI_DECISION_ALERT:
            return f"命中告警条件，触发{SEVERITY_LABELS.get(severity, severity)}告警"
        return "当前证据不足，暂不告警"

    clauses = sorted(clauses, key=lambda item: (-_score_reason_clause(item), len(item)))
    selected = [clauses[0]]
    if len(clauses) > 1:
        first_has_action = bool(re.search(r"(触发|告警|恢复|暂不告警)", selected[0]))
        second_has_action = bool(re.search(r"(触发|告警|恢复|暂不告警)", clauses[1]))
        if (not first_has_action and second_has_action) or (
            len(selected[0]) < 18 and len(clauses[1]) < 24
        ):
            selected.append(clauses[1])

    compact = "；".join(selected)
    has_action = bool(re.search(r"(触发|告警|恢复|暂不告警)", compact))
    if not has_action:
        if decision == AI_DECISION_ALERT:
            compact = f"{compact}，触发{SEVERITY_LABELS.get(severity, severity)}告警"
        elif decision == AI_DECISION_RECOVER:
            compact = f"{compact}，判定恢复"
        else:
            compact = f"{compact}，暂不告警"
    return _truncate_text(compact, max_chars=48)


def _compress_alert_ai_evidence(evidence: list[str]) -> list[str]:
    compact: list[str] = []
    seen: set[str] = set()
    for item in evidence or []:
        for clause in _split_reason_clauses(item):
            cleaned = _clean_reason_clause(clause)
            if not cleaned or _is_meta_reason_clause(cleaned):
                continue
            dedup_key = _normalize_reason_clause_for_dedup(cleaned)
            if not dedup_key or dedup_key in seen:
                continue
            seen.add(dedup_key)
            compact.append(_truncate_text(cleaned, max_chars=24))
            if len(compact) >= 2:
                return compact
    return compact


def extract_policy_severity_instruction(rule_text: str) -> tuple[Optional[str], str, Optional[str]]:
    text = (rule_text or "").strip()
    if not text:
        return None, SEVERITY_SOURCE_INFERRED, None

    for pattern in SEVERITY_RANGE_PATTERNS:
        if pattern.search(text):
            return None, SEVERITY_SOURCE_INFERRED, "模板中的等级表达属于范围提示，已按 AI 自主判断处理"

    matched: list[str] = []
    for severity, patterns in SEVERITY_EXPLICIT_PATTERNS:
        if any(pattern.search(text) for pattern in patterns):
            matched.append(severity)

    matched = list(dict.fromkeys(matched))
    if len(matched) == 1:
        return matched[0], SEVERITY_SOURCE_EXPLICIT, None
    if len(matched) > 1:
        return None, SEVERITY_SOURCE_INFERRED, "模板中存在多个明确等级表达，已按 AI 自主判断处理"
    return None, SEVERITY_SOURCE_INFERRED, None


def _severity_rank(severity: Optional[str]) -> int:
    return SEVERITY_RANKS.get((severity or "").strip().lower(), 0)


def _default_compiled_trigger_profile(
    *,
    focus_metrics: Optional[list[str]] = None,
    fallback_mode: str = "trend_heuristic",
) -> dict[str, Any]:
    return {
        "focus_metrics": list(focus_metrics or []),
        "trigger_conditions": [],
        "recovery_conditions": [],
        "escalation_rules": [],
        "fallback_mode": fallback_mode,
    }


def _merge_compiled_trigger_profile(profile: Optional[dict[str, Any]], rule_text: str) -> dict[str, Any]:
    focus_metrics = []
    if isinstance(profile, dict):
        focus_metrics = [str(item) for item in profile.get("focus_metrics") or [] if str(item).strip()]
    if not focus_metrics:
        focus_metrics = _extract_focus_metric_names(rule_text, {})

    merged = _default_compiled_trigger_profile(
        focus_metrics=focus_metrics,
        fallback_mode=(profile or {}).get("fallback_mode") if isinstance(profile, dict) else "trend_heuristic",
    )
    if not isinstance(profile, dict):
        return merged

    for key in ("trigger_conditions", "recovery_conditions", "escalation_rules"):
        values = profile.get(key) or []
        if isinstance(values, list):
            merged[key] = [item for item in values if isinstance(item, dict)]
    fallback_mode = str(profile.get("fallback_mode") or merged["fallback_mode"]).strip().lower()
    merged["fallback_mode"] = fallback_mode if fallback_mode in {"threshold_rules", "trend_heuristic"} else "trend_heuristic"
    return merged


def _detect_metric_from_text(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    for metric_name, keywords in METRIC_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return metric_name
    return None


def _detect_line_severity(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if (
        re.search(r"\bcritical\b|\bp1\b", lowered)
        or re.search(r"^\s*(?:严重|紧急)(?:[:：\s]|告警|级别|优先级)", text)
        or re.search(r"(?:严重|紧急)(?:告警|级别|优先级)", text)
    ):
        return "critical"
    if (
        re.search(r"\bhigh\b|\bp2\b", lowered)
        or re.search(r"^\s*高(?:[:：\s]|告警|级别|优先级)", text)
        or re.search(r"高(?:告警|级别|优先级)", text)
    ):
        return "high"
    if (
        re.search(r"\bmedium\b|\bp3\b", lowered)
        or re.search(r"^\s*中(?:等)?(?:[:：\s]|告警|级别|优先级)", text)
        or re.search(r"中(?:等)?(?:告警|级别|优先级)", text)
    ):
        return "medium"
    if (
        re.search(r"\blow\b|\bp4\b", lowered)
        or re.search(r"^\s*低(?:[:：\s]|告警|级别|优先级)", text)
        or re.search(r"低(?:告警|级别|优先级)", text)
    ):
        return "low"
    return None


def _extract_duration_seconds_from_text(text: str) -> Optional[int]:
    patterns = [
        re.compile(r"持续\s*(\d+(?:\.\d+)?)\s*(秒|秒钟|分钟|分|min|mins|minute|minutes)", re.IGNORECASE),
        re.compile(r"(\d+(?:\.\d+)?)\s*(秒|秒钟|分钟|分|min|mins|minute|minutes)\s*持续", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(text or "")
        if not match:
            continue
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit in {"分钟", "分", "min", "mins", "minute", "minutes"}:
            value *= 60
        return max(1, int(round(value)))
    return None


def _extract_operator_threshold_from_text(text: str) -> tuple[Optional[str], Optional[float]]:
    normalized = (text or "").replace("％", "%")
    patterns = [
        (re.compile(r"(?:>=|大于等于|不少于|不低于|至少)\s*(\d+(?:\.\d+)?)\s*%?"), ">="),
        (re.compile(r"(?:>|超过|高于|大于)\s*(\d+(?:\.\d+)?)\s*%?"), ">"),
        (re.compile(r"(?:<=|小于等于|不超过|不高于|至多)\s*(\d+(?:\.\d+)?)\s*%?"), "<="),
        (re.compile(r"(?:<|低于|小于)\s*(\d+(?:\.\d+)?)\s*%?"), "<"),
    ]
    for pattern, operator in patterns:
        match = pattern.search(normalized)
        if match:
            return operator, float(match.group(1))
    return None, None


def _sort_conditions_by_severity(conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        conditions,
        key=lambda item: (_severity_rank(item.get("severity")), float(item.get("threshold") or 0)),
    )


def _build_derived_recovery_conditions(
    trigger_conditions: list[dict[str, Any]],
    analysis_config: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for condition in trigger_conditions:
        metric = str(condition.get("metric") or "").strip()
        if not metric:
            continue
        current = grouped.get(metric)
        if current is None or float(condition.get("threshold") or 0) < float(current.get("threshold") or 0):
            grouped[metric] = condition

    recovery_conditions: list[dict[str, Any]] = []
    for metric, condition in grouped.items():
        operator = str(condition.get("operator") or ">").strip()
        threshold = float(condition.get("threshold") or 0)
        duration_seconds = int(condition.get("duration_seconds") or 0) or (
            int(analysis_config.get("min_recovery_consecutive_samples", 2)) * 60
        )
        if operator in {">", ">="}:
            recovery_operator = "<="
        else:
            recovery_operator = ">="
        recovery_conditions.append(
            {
                "metric": metric,
                "operator": recovery_operator,
                "threshold": threshold,
                "duration_seconds": duration_seconds,
            }
        )
    return recovery_conditions


def _compile_policy_profile_locally(
    rule_text: str,
    analysis_config: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], bool, Optional[str]]:
    config = normalize_analysis_config(analysis_config)
    lines = [line.strip("；;。 \t") for line in re.split(r"[\n\r]+", rule_text or "") if line.strip()]
    if len(lines) <= 1:
        lines = [segment.strip("；;。 \t") for segment in re.split(r"[；;]", rule_text or "") if segment.strip()]

    trigger_conditions: list[dict[str, Any]] = []
    recovery_conditions: list[dict[str, Any]] = []
    focus_metrics: list[str] = []
    full_text_focus_metrics = _extract_focus_metric_names(rule_text, {})

    for line in lines:
        for metric_name in _extract_focus_metric_names(line, {}):
            if metric_name not in focus_metrics:
                focus_metrics.append(metric_name)
        metric = _detect_metric_from_text(line)
        operator, threshold = _extract_operator_threshold_from_text(line)
        duration_seconds = _extract_duration_seconds_from_text(line) or 0
        severity = _detect_line_severity(line)

        if metric and metric not in focus_metrics:
            focus_metrics.append(metric)
        if not metric or threshold is None:
            continue

        condition = {
            "metric": metric,
            "operator": operator or ">",
            "threshold": round(float(threshold), 4),
            "duration_seconds": duration_seconds or 0,
        }
        if severity:
            condition["severity"] = severity

        if "恢复" in line or "回落" in line:
            recovery_conditions.append(condition)
        else:
            trigger_conditions.append(condition)

    if not focus_metrics:
        focus_metrics = list(full_text_focus_metrics)
    else:
        for metric_name in full_text_focus_metrics:
            if metric_name not in focus_metrics:
                focus_metrics.append(metric_name)

    trigger_conditions = _sort_conditions_by_severity(trigger_conditions)
    escalation_rules = [item for item in trigger_conditions if item.get("severity")]
    if not recovery_conditions and trigger_conditions:
        recovery_conditions = _build_derived_recovery_conditions(trigger_conditions, config)

    fallback_mode = "threshold_rules" if (trigger_conditions or focus_metrics) else "trend_heuristic"
    profile = {
        "focus_metrics": focus_metrics,
        "trigger_conditions": trigger_conditions,
        "recovery_conditions": recovery_conditions,
        "escalation_rules": escalation_rules,
        "fallback_mode": fallback_mode,
    }
    complete = bool(trigger_conditions)
    error = None if complete else "本地解析未提取到明确触发条件，将回退到阈值/趋势预筛选"
    return profile, complete, error


def _normalize_compiled_condition(item: dict[str, Any], *, allow_severity: bool) -> Optional[dict[str, Any]]:
    metric = str(item.get("metric") or "").strip()
    operator = str(item.get("operator") or "").strip() or ">"
    threshold = _to_float(item.get("threshold"))
    if not metric or threshold is None or operator not in {">", ">=", "<", "<="}:
        return None

    normalized = {
        "metric": metric,
        "operator": operator,
        "threshold": round(threshold, 4),
        "duration_seconds": max(0, int(_to_float(item.get("duration_seconds")) or 0)),
    }
    if allow_severity:
        severity = str(item.get("severity") or "").strip().lower()
        if severity in AI_ALLOWED_SEVERITIES:
            normalized["severity"] = severity
    return normalized


def _normalize_compiled_profile(raw: dict[str, Any], rule_text: str) -> dict[str, Any]:
    profile = _default_compiled_trigger_profile(
        focus_metrics=[str(item) for item in raw.get("focus_metrics") or [] if str(item).strip()],
        fallback_mode=str(raw.get("fallback_mode") or "trend_heuristic").strip().lower(),
    )
    if not profile["focus_metrics"]:
        profile["focus_metrics"] = _extract_focus_metric_names(rule_text, {})

    for key, allow_severity in (
        ("trigger_conditions", True),
        ("recovery_conditions", False),
        ("escalation_rules", True),
    ):
        values = raw.get(key) or []
        if not isinstance(values, list):
            continue
        normalized_values = []
        for item in values:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_compiled_condition(item, allow_severity=allow_severity)
            if normalized:
                normalized_values.append(normalized)
        profile[key] = normalized_values

    if profile["fallback_mode"] not in {"threshold_rules", "trend_heuristic"}:
        profile["fallback_mode"] = "trend_heuristic"
    return profile


def _extract_focus_metric_names(rule_text: str, current_metrics: dict[str, Any]) -> list[str]:
    text = (rule_text or "").lower()
    selected: list[str] = []
    for metric_name, keywords in METRIC_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            selected.append(metric_name)

    for metric_name in PREFERRED_METRICS:
        if metric_name not in selected and _extract_metric_value(current_metrics, metric_name) is not None:
            selected.append(metric_name)

    if not selected:
        for key in current_metrics.keys():
            if len(selected) >= MAX_FEATURE_METRICS:
                break
            if _to_float(current_metrics.get(key)) is not None:
                selected.append(str(key))

    return selected[:MAX_FEATURE_METRICS]


def _find_snapshot_value_at_window(
    snapshots_desc: list[DatasourceMetric],
    metric_name: str,
    reference_time: datetime,
    seconds: int,
) -> Optional[float]:
    target_time = reference_time - timedelta(seconds=seconds)
    for snapshot in snapshots_desc:
        if snapshot.collected_at <= target_time:
            return _extract_metric_value(snapshot.data or {}, metric_name)
    return None


def _resolve_sampling_interval_seconds(
    snapshots_desc: list[DatasourceMetric],
    configured_interval_seconds: Optional[int] = None,
) -> int:
    configured_interval = _to_float(configured_interval_seconds)
    if configured_interval and configured_interval > 0:
        return max(1, int(round(configured_interval)))

    diffs: list[float] = []
    previous_time: Optional[datetime] = None
    for snapshot in snapshots_desc:
        if previous_time is not None:
            gap_seconds = (previous_time - snapshot.collected_at).total_seconds()
            if gap_seconds > 0:
                diffs.append(gap_seconds)
        previous_time = snapshot.collected_at
        if len(diffs) >= 5:
            break

    if diffs:
        sorted_diffs = sorted(diffs)
        return max(1, int(round(sorted_diffs[len(sorted_diffs) // 2])))

    return 60


def _build_recent_samples(
    snapshots_desc: list[DatasourceMetric],
    metric_name: str,
    sample_limit: int = MAX_RECENT_SAMPLES_PER_METRIC,
) -> list[dict[str, Any]]:
    samples_desc: list[dict[str, Any]] = []
    for snapshot in snapshots_desc:
        value = _extract_metric_value(snapshot.data or {}, metric_name)
        if value is None:
            continue
        samples_desc.append(
            {
                "collected_at": snapshot.collected_at.isoformat(),
                "value": round(value, 4),
            }
        )
        if len(samples_desc) >= sample_limit:
            break
    samples_desc.reverse()
    return samples_desc


def _build_metric_features(
    snapshots_desc: list[DatasourceMetric],
    current_metrics: dict[str, Any],
    metric_names: Iterable[str],
    collected_at: datetime,
) -> dict[str, Any]:
    metric_features: dict[str, Any] = {}
    for metric_name in metric_names:
        current_value = _extract_metric_value(current_metrics, metric_name)
        if current_value is None:
            continue

        historical_values = [
            value
            for value in (
                _extract_metric_value(snapshot.data or {}, metric_name)
                for snapshot in snapshots_desc
            )
            if value is not None
        ]
        avg_24h = round(sum(historical_values) / len(historical_values), 4) if historical_values else None
        baseline_min = round(min(historical_values), 4) if historical_values else None
        baseline_max = round(max(historical_values), 4) if historical_values else None

        value_5m = _find_snapshot_value_at_window(snapshots_desc, metric_name, collected_at, 300)
        value_15m = _find_snapshot_value_at_window(snapshots_desc, metric_name, collected_at, 900)
        value_60m = _find_snapshot_value_at_window(snapshots_desc, metric_name, collected_at, 3600)
        recent_samples = _build_recent_samples(snapshots_desc, metric_name)
        recent_span_seconds = 0
        if len(recent_samples) >= 2:
            start_time = datetime.fromisoformat(str(recent_samples[0]["collected_at"]))
            end_time = datetime.fromisoformat(str(recent_samples[-1]["collected_at"]))
            recent_span_seconds = max(0, int(round((end_time - start_time).total_seconds())))

        metric_features[metric_name] = {
            "current": round(current_value, 4),
            "value_5m_ago": round(value_5m, 4) if value_5m is not None else None,
            "value_15m_ago": round(value_15m, 4) if value_15m is not None else None,
            "value_60m_ago": round(value_60m, 4) if value_60m is not None else None,
            "delta_5m": round(current_value - value_5m, 4) if value_5m is not None else None,
            "delta_15m": round(current_value - value_15m, 4) if value_15m is not None else None,
            "delta_60m": round(current_value - value_60m, 4) if value_60m is not None else None,
            "avg_24h": avg_24h,
            "min_24h": baseline_min,
            "max_24h": baseline_max,
            "recent_samples": recent_samples,
            "recent_sample_count": len(recent_samples),
            "recent_samples_span_seconds": recent_span_seconds,
        }
    return metric_features


def _get_metric_recent_values(metric_feature: dict[str, Any], sample_count: int) -> list[float]:
    values = [item.get("value") for item in metric_feature.get("recent_samples") or []]
    normalized = [float(value) for value in values if value is not None]
    if sample_count <= 0:
        return normalized
    return normalized[-sample_count:]


def _value_satisfies_operator(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    return False


def _bucket_metric_value(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    absolute = abs(value)
    if absolute >= 100:
        return round(value / 10.0) * 10.0
    if absolute >= 10:
        return round(value / 5.0) * 5.0
    return round(value, 1)


def _estimate_required_samples(duration_seconds: int, sampling_interval_seconds: int) -> int:
    if duration_seconds <= 0:
        return 1
    if duration_seconds <= sampling_interval_seconds:
        return 1
    return max(1, math.ceil(duration_seconds / max(sampling_interval_seconds, 1)))


def _evaluate_condition(
    condition: dict[str, Any],
    metric_features: dict[str, Any],
    sampling_interval_seconds: int,
) -> dict[str, Any]:
    metric = str(condition.get("metric") or "").strip()
    metric_feature = metric_features.get(metric) or {}
    current = _to_float(metric_feature.get("current"))
    threshold = _to_float(condition.get("threshold"))
    operator = str(condition.get("operator") or ">").strip()
    duration_seconds = int(condition.get("duration_seconds") or 0)
    required_samples = _estimate_required_samples(duration_seconds, sampling_interval_seconds)
    recent_values = _get_metric_recent_values(metric_feature, required_samples)
    matched = bool(
        current is not None
        and threshold is not None
        and len(recent_values) >= required_samples
        and all(_value_satisfies_operator(value, operator, threshold) for value in recent_values)
    )
    coverage_seconds = sampling_interval_seconds * max(len(recent_values) - 1, 0)
    return {
        **condition,
        "current": current,
        "matched": matched,
        "required_samples": required_samples,
        "coverage_seconds": coverage_seconds,
    }


def _is_trending_towards_threshold(
    metric_feature: dict[str, Any],
    operator: str,
    sample_count: int,
) -> bool:
    recent_values = _get_metric_recent_values(metric_feature, sample_count)
    if len(recent_values) < 2:
        return False
    start = recent_values[0]
    end = recent_values[-1]
    if operator in {">", ">="}:
        return end > start and recent_values[-1] >= recent_values[-2]
    return end < start and recent_values[-1] <= recent_values[-2]


def _is_near_threshold(
    current: Optional[float],
    operator: str,
    threshold: Optional[float],
    near_ratio: float,
) -> bool:
    if current is None or threshold is None:
        return False
    if operator in {">", ">="}:
        return current >= threshold * near_ratio
    if threshold == 0:
        return current <= 0
    return current <= threshold * (2 - near_ratio)


def _build_candidate_fingerprint(
    candidate_type: str,
    matched_conditions: list[dict[str, Any]],
    metric_features: dict[str, Any],
    severity_hint: Optional[str],
) -> str:
    payload = {
        "candidate_type": candidate_type,
        "severity": severity_hint or "",
        "metrics": [
            {
                "metric": item.get("metric"),
                "threshold": item.get("threshold"),
                "current_bucket": _bucket_metric_value(_to_float((metric_features.get(item.get("metric")) or {}).get("current"))),
                "delta_15m": _bucket_metric_value(_to_float((metric_features.get(item.get("metric")) or {}).get("delta_15m"))),
            }
            for item in matched_conditions
        ],
    }
    return hashlib.sha256(_json_dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _merge_gate_skip_reason(skip_map: Any, reason: str) -> dict[str, int]:
    merged = dict(skip_map or {})
    merged[reason] = int(merged.get(reason, 0) or 0) + 1
    return merged


def _build_fallback_threshold_conditions(
    threshold_rules: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(threshold_rules, dict):
        return []
    conditions = []
    for metric_name, rule in threshold_rules.items():
        if not isinstance(rule, dict):
            continue
        threshold = _to_float(rule.get("threshold"))
        if threshold is None:
            continue
        conditions.append(
            {
                "metric": str(metric_name),
                "operator": ">",
                "threshold": round(threshold, 4),
                "duration_seconds": max(0, int(_to_float(rule.get("duration")) or 0)),
            }
        )
    return conditions


def _build_trend_candidate(
    focus_metrics: list[str],
    metric_features: dict[str, Any],
    analysis_config: dict[str, Any],
) -> Optional[AlertAIGateDecision]:
    trend_window = int(analysis_config.get("trend_window_samples", 5) or 5)
    for metric in focus_metrics:
        feature = metric_features.get(metric)
        if not feature:
            continue
        current = _to_float(feature.get("current"))
        avg_24h = _to_float(feature.get("avg_24h"))
        delta_15m = _to_float(feature.get("delta_15m"))
        if current is None or avg_24h is None or delta_15m is None:
            continue
        if avg_24h <= 0:
            continue
        if current >= avg_24h * 1.5 and delta_15m > 0 and _is_trending_towards_threshold(feature, ">", trend_window):
            matched = [{"metric": metric, "operator": ">", "threshold": round(avg_24h, 4), "current": current}]
            return AlertAIGateDecision(
                should_evaluate=True,
                candidate_type="trend",
                fingerprint=_build_candidate_fingerprint("trend", matched, metric_features, None),
                severity_hint=None,
                reason=f"{metric} 明显高于 24 小时均值且持续上升",
                gate_reason="trend_candidate",
                matched_conditions=matched,
                gate_metrics={metric: {"current": current, "avg_24h": avg_24h, "delta_15m": delta_15m}},
            )
    return None


async def build_alert_ai_feature_summary(
    db: AsyncSession,
    datasource,
    rule_text: str,
    current_metrics: dict[str, Any],
    collected_at: datetime,
    *,
    compiled_trigger_profile: Optional[dict[str, Any]] = None,
    runtime_state: Optional[AlertAIRuntimeState] = None,
    gate_decision: Optional[AlertAIGateDecision] = None,
    snapshots_desc: Optional[list[DatasourceMetric]] = None,
    sampling_interval_seconds: Optional[int] = None,
) -> dict[str, Any]:
    from backend.services.monitoring_scheduler_service import get_monitoring_collection_interval_seconds

    if snapshots_desc is None:
        result = await db.execute(
            select(DatasourceMetric)
            .where(
                DatasourceMetric.datasource_id == datasource.id,
                DatasourceMetric.metric_type == "db_status",
                DatasourceMetric.collected_at >= collected_at - timedelta(hours=24),
            )
            .order_by(desc(DatasourceMetric.collected_at))
            .limit(MAX_HISTORY_SNAPSHOTS)
        )
        snapshots_desc = result.scalars().all()

    active_alerts_result = await db.execute(
        select(AlertMessage)
        .where(
            AlertMessage.datasource_id == datasource.id,
            AlertMessage.status.in_(["active", "acknowledged"]),
        )
        .order_by(AlertMessage.created_at.desc())
        .limit(1)
    )
    active_alerts = active_alerts_result.scalars().all()

    profile = _merge_compiled_trigger_profile(compiled_trigger_profile, rule_text)
    metric_names = list(profile.get("focus_metrics") or []) or _extract_focus_metric_names(rule_text, current_metrics)
    metric_features = _build_metric_features(snapshots_desc, current_metrics, metric_names, collected_at)
    if sampling_interval_seconds is None:
        try:
            sampling_interval_seconds = await get_monitoring_collection_interval_seconds(db)
        except ValueError:
            sampling_interval_seconds = None
    sampling_interval_seconds = _resolve_sampling_interval_seconds(snapshots_desc, sampling_interval_seconds)
    compact_metric_features = {
        metric: {
            "current": feature.get("current"),
            "delta_15m": feature.get("delta_15m"),
            "avg_24h": feature.get("avg_24h"),
            "recent_samples": feature.get("recent_samples"),
            "recent_sample_count": feature.get("recent_sample_count"),
            "recent_samples_span_seconds": feature.get("recent_samples_span_seconds"),
        }
        for metric, feature in metric_features.items()
    }

    return {
        "datasource": {
            "id": datasource.id,
            "name": datasource.name,
            "db_type": datasource.db_type,
            "importance_level": datasource.importance_level or "production",
        },
        "collected_at": collected_at.isoformat(),
        "sampling_interval_seconds": sampling_interval_seconds,
        "focus_metrics": metric_names,
        "metric_features": compact_metric_features,
        "compiled_trigger_profile": {
            "trigger_conditions": profile.get("trigger_conditions") or [],
            "recovery_conditions": profile.get("recovery_conditions") or [],
            "escalation_rules": profile.get("escalation_rules") or [],
            "fallback_mode": profile.get("fallback_mode") or "trend_heuristic",
        },
        "runtime_state": {
            "active": bool(runtime_state.is_active) if runtime_state else False,
            "last_decision": getattr(runtime_state, "last_decision", None),
            "last_triggered_at": runtime_state.last_triggered_at.isoformat() if runtime_state and runtime_state.last_triggered_at else None,
            "last_recovered_at": runtime_state.last_recovered_at.isoformat() if runtime_state and runtime_state.last_recovered_at else None,
        },
        "candidate": {
            "type": gate_decision.candidate_type if gate_decision else None,
            "reason": gate_decision.reason if gate_decision else None,
            "severity_hint": gate_decision.severity_hint if gate_decision else None,
            "matched_conditions": gate_decision.matched_conditions if gate_decision else [],
            "gate_metrics": gate_decision.gate_metrics if gate_decision else {},
        },
        "active_alerts": [
            {
                "id": alert.id,
                "severity": alert.severity,
                "metric_name": alert.metric_name,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
            for alert in active_alerts
        ],
    }


def _extract_json_from_text(text: str) -> Optional[dict[str, Any]]:
    content = (text or "").strip()
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_judge_result(parsed: dict[str, Any], raw_response: str) -> AlertAIJudgeResult:
    decision = str(parsed.get("decision", AI_DECISION_NO_ALERT)).strip().lower()
    if decision not in AI_ALLOWED_DECISIONS:
        raise ValueError(f"unsupported decision: {decision}")

    severity_raw = parsed.get("severity")
    if severity_raw is None:
        raise ValueError("模型返回缺少 severity 字段")
    severity = str(severity_raw).strip().lower()
    if severity not in AI_ALLOWED_SEVERITIES:
        raise ValueError(f"模型返回非法 severity: {severity_raw}")

    confidence_raw = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    evidence = parsed.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]

    return AlertAIJudgeResult(
        decision=decision,
        severity=severity,
        confidence=confidence,
        reason=str(parsed.get("reason", "") or "").strip(),
        evidence=[str(item).strip() for item in evidence if str(item).strip()],
        trigger_inspection=bool(parsed.get("trigger_inspection", False)),
        raw_response=raw_response,
        severity_source=SEVERITY_SOURCE_INFERRED,
    )


async def resolve_alert_ai_policy_binding(
    db: AsyncSession,
    *,
    ai_policy_source: Optional[str],
    ai_policy_text: Optional[str],
    ai_policy_id: Optional[int],
    alert_ai_model_id: Optional[int],
) -> Optional[AlertAIPolicyBinding]:
    source = normalize_ai_policy_source(ai_policy_source)
    model_id = alert_ai_model_id

    if source == "template":
        if not ai_policy_id:
            return None
        result = await db.execute(select(AlertAIPolicy).where(AlertAIPolicy.id == ai_policy_id))
        policy = result.scalar_one_or_none()
        if not policy or not policy.is_enabled:
            return None
        policy = await ensure_alert_ai_policy_compiled(db, policy)
        rule_text = (policy.rule_text or "").strip()
        if not rule_text:
            return None
        model_id = model_id or policy.model_id
        display_name = policy.name
        policy_id = policy.id
        analysis_strategy = normalize_analysis_strategy(policy.analysis_strategy)
        analysis_config = normalize_analysis_config(policy.analysis_config)
        compiled_trigger_profile = _merge_compiled_trigger_profile(policy.compiled_trigger_profile, rule_text)
        compile_status = policy.compile_status or "pending"
        compile_error = policy.compile_error
        compiled_at = policy.compiled_at
    else:
        rule_text = (ai_policy_text or "").strip()
        if not rule_text:
            return None
        display_name = INLINE_AI_POLICY_DISPLAY_NAME
        policy_id = None
        analysis_strategy = DEFAULT_ANALYSIS_STRATEGY
        analysis_config = normalize_analysis_config(None)
        compiled_profile, _complete, compile_error = _compile_policy_profile_locally(rule_text, analysis_config)
        compiled_trigger_profile = _merge_compiled_trigger_profile(compiled_profile, rule_text)
        compile_status = "ready" if compiled_trigger_profile.get("trigger_conditions") else "failed"
        compiled_at = None

    fingerprint = hashlib.sha256(f"{source}:{policy_id or 'inline'}:{rule_text}".encode("utf-8")).hexdigest()
    policy_severity_hint, severity_constraint_mode, severity_warning = extract_policy_severity_instruction(rule_text)
    return AlertAIPolicyBinding(
        policy_id=policy_id,
        policy_source=source,
        rule_text=rule_text,
        model_id=model_id,
        policy_fingerprint=fingerprint,
        display_name=display_name,
        policy_severity_hint=policy_severity_hint,
        severity_constraint_mode=severity_constraint_mode,
        severity_warning=severity_warning,
        analysis_strategy=analysis_strategy,
        analysis_config=analysis_config,
        compiled_trigger_profile=compiled_trigger_profile,
        compile_status=compile_status,
        compile_error=compile_error,
        compiled_at=compiled_at,
    )


async def resolve_configured_alert_ai_policy_binding(db: AsyncSession, config) -> Optional[AlertAIPolicyBinding]:
    return await resolve_alert_ai_policy_binding(
        db,
        ai_policy_source=getattr(config, "ai_policy_source", None),
        ai_policy_text=getattr(config, "ai_policy_text", None),
        ai_policy_id=getattr(config, "ai_policy_id", None),
        alert_ai_model_id=getattr(config, "alert_ai_model_id", None),
    )


async def resolve_alert_ai_client(db: AsyncSession, preferred_model_id: Optional[int] = None):
    model = None
    if preferred_model_id:
        result = await db.execute(
            select(AIModel).where(AIModel.id == preferred_model_id, AIModel.is_active == True)
        )
        model = result.scalar_one_or_none()

    if not model:
        result = await db.execute(
            select(AIModel)
            .where(AIModel.is_active == True, AIModel.is_default == True)
            .limit(1)
        )
        model = result.scalar_one_or_none()

    if not model:
        result = await db.execute(
            select(AIModel).where(AIModel.is_active == True).order_by(AIModel.id.asc()).limit(1)
        )
        model = result.scalar_one_or_none()

    if not model:
        return None, None

    try:
        api_key = decrypt_value(model.api_key_encrypted)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to decrypt AI model key for alert judge model_id=%s: %s", model.id, exc)
        return None, None

    client = get_ai_client(
        api_key=api_key,
        base_url=model.base_url,
        model_name=model.model_name,
        protocol=getattr(model, "protocol", "openai"),
        reasoning_effort=getattr(model, "reasoning_effort", None),
    )
    return client, model


async def _compile_policy_profile_with_ai(
    db: AsyncSession,
    *,
    rule_text: str,
    preferred_model_id: Optional[int],
    local_profile: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    client, _model = await resolve_alert_ai_client(db, preferred_model_id=preferred_model_id)
    if not client:
        return None, "未配置可用 AI 模型，无法补全模板编译结果"

    system_prompt = (
        "你是数据库告警模板编译器。"
        "请把自然语言告警模板编译成结构化 JSON，只返回 JSON。"
        '格式必须是 {"focus_metrics":["cpu_usage"],"trigger_conditions":[{"metric":"cpu_usage","operator":">","threshold":80,"duration_seconds":60,"severity":"high"}],"recovery_conditions":[{"metric":"cpu_usage","operator":"<=","threshold":80,"duration_seconds":120}],"escalation_rules":[{"metric":"cpu_usage","operator":">","threshold":90,"duration_seconds":60,"severity":"critical"}],"fallback_mode":"threshold_rules|trend_heuristic"}。'
        "metric 只能使用已知监控指标名，例如 cpu_usage、memory_usage、disk_usage、connections_active、connections_total、connections_waiting、qps、tps、iops、throughput、cache_hit_rate、lock_waiting、longest_transaction_sec。"
        "operator 只能是 >、>=、<、<=。"
        "无法确认的部分留空数组，并根据可结构化程度选择 fallback_mode。"
    )
    user_payload = {
        "rule_text": rule_text,
        "local_profile": local_profile,
    }
    try:
        raw_response, _usage = await asyncio.wait_for(
            request_text_response_with_usage(
                client,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _json_dumps(user_payload)},
                ],
                temperature=0,
                max_tokens=320,
            ),
            timeout=min(5, await get_ai_alert_timeout_seconds(db)),
        )
    except Exception as exc:
        return None, f"AI 编译失败：{exc}"

    parsed = _extract_json_from_text(raw_response)
    if not isinstance(parsed, dict):
        return None, "AI 编译失败：模型未返回合法 JSON"
    return _normalize_compiled_profile(parsed, rule_text), None


async def compile_alert_ai_policy(policy: AlertAIPolicy, db: AsyncSession) -> AlertAIPolicy:
    local_profile, complete, local_error = _compile_policy_profile_locally(
        policy.rule_text or "",
        getattr(policy, "analysis_config", None),
    )
    compiled_profile = local_profile
    compile_error = local_error
    compile_status = "ready" if complete else "failed"

    if not complete:
        ai_profile, ai_error = await _compile_policy_profile_with_ai(
            db,
            rule_text=policy.rule_text or "",
            preferred_model_id=getattr(policy, "model_id", None),
            local_profile=local_profile,
        )
        if ai_profile:
            compiled_profile = _merge_compiled_trigger_profile(ai_profile, policy.rule_text or "")
            compile_error = None
            compile_status = "ready"
        elif ai_error:
            compile_error = ai_error if not compile_error else f"{compile_error}；{ai_error}"

    policy.analysis_strategy = normalize_analysis_strategy(getattr(policy, "analysis_strategy", None))
    policy.analysis_config = normalize_analysis_config(getattr(policy, "analysis_config", None))
    policy.compiled_trigger_profile = _merge_compiled_trigger_profile(compiled_profile, policy.rule_text or "")
    policy.compile_status = compile_status
    policy.compile_error = compile_error
    policy.compiled_at = now()
    return policy


async def ensure_alert_ai_policy_compiled(db: AsyncSession, policy: AlertAIPolicy) -> AlertAIPolicy:
    analysis_config = normalize_analysis_config(getattr(policy, "analysis_config", None))
    existing_profile = _merge_compiled_trigger_profile(getattr(policy, "compiled_trigger_profile", None), policy.rule_text or "")
    _severity_hint, _constraint_mode, severity_warning = extract_policy_severity_instruction(policy.rule_text or "")
    should_refresh_for_severity = bool(
        severity_warning
        and "多个明确等级表达" in severity_warning
        and existing_profile.get("trigger_conditions")
        and sum(1 for item in existing_profile.get("trigger_conditions") or [] if item.get("severity")) < 2
    )
    needs_compile = (
        not getattr(policy, "compiled_at", None)
        or not getattr(policy, "compiled_trigger_profile", None)
        or normalize_analysis_strategy(getattr(policy, "analysis_strategy", None)) != getattr(policy, "analysis_strategy", None)
        or analysis_config != (getattr(policy, "analysis_config", None) or {})
        or should_refresh_for_severity
    )
    if not needs_compile:
        policy.analysis_config = analysis_config
        policy.analysis_strategy = normalize_analysis_strategy(getattr(policy, "analysis_strategy", None))
        return policy

    await compile_alert_ai_policy(policy, db)
    await db.flush()
    return policy


async def get_or_create_runtime_state(
    db: AsyncSession,
    datasource_id: int,
    binding: AlertAIPolicyBinding,
) -> AlertAIRuntimeState:
    result = await db.execute(
        select(AlertAIRuntimeState).where(
            AlertAIRuntimeState.datasource_id == datasource_id,
            AlertAIRuntimeState.policy_fingerprint == binding.policy_fingerprint,
        )
    )
    state = result.scalar_one_or_none()
    if state:
        return state

    state = AlertAIRuntimeState(
        datasource_id=datasource_id,
        policy_id=binding.policy_id,
        policy_source=binding.policy_source,
        policy_fingerprint=binding.policy_fingerprint,
        is_active=False,
        consecutive_alert_count=0,
        consecutive_recover_count=0,
    )
    db.add(state)
    await db.flush()
    return state


async def _resolve_current_alert_severity(
    db: AsyncSession,
    datasource_id: int,
    state: AlertAIRuntimeState,
    binding: AlertAIPolicyBinding,
) -> Optional[str]:
    alert = None
    if state.alert_id:
        alert = await db.get(AlertMessage, state.alert_id)
    if not alert or alert.status not in {"active", "acknowledged"}:
        alert = await _find_active_ai_alert(db, datasource_id, binding.display_name)
    return getattr(alert, "severity", None) if alert else None


def decide_alert_ai_candidate(
    *,
    binding: AlertAIPolicyBinding,
    state: AlertAIRuntimeState,
    current_metrics: dict[str, Any],
    collected_at: datetime,
    snapshots_desc: list[DatasourceMetric],
    threshold_rules: Optional[dict[str, Any]] = None,
    current_alert_severity: Optional[str] = None,
    datasource=None,
    sampling_interval_seconds: Optional[int] = None,
) -> tuple[AlertAIGateDecision, dict[str, Any]]:
    profile = _merge_compiled_trigger_profile(binding.compiled_trigger_profile, binding.rule_text)
    analysis_config = normalize_analysis_config(binding.analysis_config)
    focus_metrics = list(profile.get("focus_metrics") or []) or _extract_focus_metric_names(binding.rule_text, current_metrics)
    metric_features = _build_metric_features(snapshots_desc, current_metrics, focus_metrics, collected_at)
    sampling_interval_seconds = _resolve_sampling_interval_seconds(snapshots_desc, sampling_interval_seconds)
    trend_window = int(analysis_config.get("trend_window_samples", 5) or 5)
    near_ratio = float(analysis_config.get("near_threshold_ratio", 0.9) or 0.9)
    fallback_mode = profile.get("fallback_mode") or "trend_heuristic"

    trigger_conditions = profile.get("trigger_conditions") or []
    if not trigger_conditions and fallback_mode == "threshold_rules":
        trigger_conditions = _build_fallback_threshold_conditions(threshold_rules)
    recovery_conditions = profile.get("recovery_conditions") or []
    escalation_rules = profile.get("escalation_rules") or []

    if not state.is_active:
        matched_triggers = [
            _evaluate_condition(condition, metric_features, sampling_interval_seconds)
            for condition in trigger_conditions
        ]
        direct_matches = [item for item in matched_triggers if item.get("matched")]
        if direct_matches:
            severity_hint = max(
                (item.get("severity") for item in direct_matches if item.get("severity")),
                key=_severity_rank,
                default=None,
            )
            return AlertAIGateDecision(
                should_evaluate=True,
                candidate_type="trigger",
                fingerprint=_build_candidate_fingerprint("trigger", direct_matches, metric_features, severity_hint),
                severity_hint=severity_hint,
                reason="命中结构化触发条件",
                gate_reason="candidate_trigger",
                matched_conditions=direct_matches,
                gate_metrics={metric: metric_features.get(metric) for metric in focus_metrics if metric in metric_features},
            ), metric_features

        for item in matched_triggers:
            metric = item.get("metric")
            feature = metric_features.get(metric) or {}
            current = _to_float(feature.get("current"))
            threshold = _to_float(item.get("threshold"))
            operator = str(item.get("operator") or ">")
            if _is_near_threshold(current, operator, threshold, near_ratio) and _is_trending_towards_threshold(feature, operator, trend_window):
                matched = [item]
                return AlertAIGateDecision(
                    should_evaluate=True,
                    candidate_type="near_threshold",
                    fingerprint=_build_candidate_fingerprint("near_threshold", matched, metric_features, item.get("severity")),
                    severity_hint=item.get("severity"),
                    reason=f"{metric} 接近阈值且趋势持续朝触发方向变化",
                    gate_reason="candidate_near_threshold",
                    matched_conditions=matched,
                    gate_metrics={metric: feature},
                ), metric_features

        trend_candidate = _build_trend_candidate(focus_metrics, metric_features, analysis_config)
        if trend_candidate:
            return trend_candidate, metric_features

        return AlertAIGateDecision(
            should_evaluate=False,
            candidate_type="none",
            fingerprint=None,
            severity_hint=None,
            reason="未命中任何 AI 候选条件",
            gate_reason="no_candidate",
            matched_conditions=[],
            gate_metrics={metric: metric_features.get(metric) for metric in focus_metrics if metric in metric_features},
        ), metric_features

    matched_recoveries = [
        _evaluate_condition(condition, metric_features, sampling_interval_seconds)
        for condition in recovery_conditions
    ]
    direct_recoveries = [item for item in matched_recoveries if item.get("matched")]
    if direct_recoveries:
        return AlertAIGateDecision(
            should_evaluate=True,
            candidate_type="recovery",
            fingerprint=_build_candidate_fingerprint("recovery", direct_recoveries, metric_features, current_alert_severity),
            severity_hint=current_alert_severity,
            reason="命中恢复候选条件",
            gate_reason="candidate_recovery",
            matched_conditions=direct_recoveries,
            gate_metrics={metric: metric_features.get(metric) for metric in focus_metrics if metric in metric_features},
        ), metric_features

    matched_escalations = [
        _evaluate_condition(condition, metric_features, sampling_interval_seconds)
        for condition in escalation_rules
    ]
    direct_escalations = [
        item for item in matched_escalations
        if item.get("matched") and _severity_rank(item.get("severity")) > _severity_rank(current_alert_severity)
    ]
    if direct_escalations:
        severity_hint = max(
            (item.get("severity") for item in direct_escalations if item.get("severity")),
            key=_severity_rank,
            default=current_alert_severity,
        )
        return AlertAIGateDecision(
            should_evaluate=True,
            candidate_type="escalation",
            fingerprint=_build_candidate_fingerprint("escalation", direct_escalations, metric_features, severity_hint),
            severity_hint=severity_hint,
            reason="命中更高严重等级候选条件",
            gate_reason="candidate_escalation",
            matched_conditions=direct_escalations,
            gate_metrics={metric: metric_features.get(metric) for metric in focus_metrics if metric in metric_features},
        ), metric_features

    backstop_seconds = int(analysis_config.get("active_backstop_eval_seconds", 1800) or 1800)
    if not state.last_ai_evaluated_at or (collected_at - state.last_ai_evaluated_at).total_seconds() >= backstop_seconds:
        matched = [{"metric": metric, "current": (metric_features.get(metric) or {}).get("current")} for metric in focus_metrics]
        return AlertAIGateDecision(
            should_evaluate=True,
            candidate_type="backstop",
            fingerprint=_build_candidate_fingerprint("backstop", matched, metric_features, current_alert_severity),
            severity_hint=current_alert_severity,
            reason="活跃告警进入低频兜底复判窗口",
            gate_reason="candidate_backstop",
            matched_conditions=matched,
            gate_metrics={metric: metric_features.get(metric) for metric in focus_metrics if metric in metric_features},
        ), metric_features

    return AlertAIGateDecision(
        should_evaluate=False,
        candidate_type="none",
        fingerprint=None,
        severity_hint=current_alert_severity,
        reason="当前活跃告警未达到恢复、升级或兜底复判条件",
        gate_reason="no_active_candidate",
        matched_conditions=[],
        gate_metrics={metric: metric_features.get(metric) for metric in focus_metrics if metric in metric_features},
    ), metric_features


def _build_alert_ai_messages(
    binding: AlertAIPolicyBinding,
    feature_summary: dict[str, Any],
    state: AlertAIRuntimeState,
) -> list[dict[str, Any]]:
    analysis_config = normalize_analysis_config(binding.analysis_config)
    system_prompt = (
        "你是数据库告警判警引擎。"
        "你只根据自然语言告警规则和结构化指标摘要判断当前是否应该触发告警、保持无告警或判定恢复。"
        "不要输出分析过程，不要补充额外文字，只返回 JSON。"
        "如果证据不足或数据不完整，优先返回 no_alert 且低置信度。"
        "feature_summary.metric_features 中只包含重点指标的最近样本、15 分钟变化和 24 小时基线。"
        "feature_summary.sampling_interval_seconds 表示采样间隔秒数，recent_samples 按时间正序排列，可直接用于判断持续时间条件。"
        "当 recent_samples 已覆盖要求持续窗口且相关样本持续满足阈值时，不要因为没有额外的 duration 字段就判定证据不足。"
        "如果采样粒度明显粗于模板要求的持续时间，可以简短说明按当前样本判断，但不要展开分析过程。"
        "reason 必须是一句简短中文结论，控制在 18 到 40 个字内，只保留结论和最核心依据。"
        "不要重复同一事实，不要列出多个时间点，不要输出模板解析说明，不要输出“模板中存在多个明确等级表达”之类元信息。"
        "evidence 最多返回 2 条，每条不超过 18 个字。"
        "如果 policy.severity_constraint_mode 为 explicit，则你必须返回与 policy.policy_severity_hint 完全一致的 severity。"
        'JSON 格式必须是 {"decision":"alert|no_alert|recover","severity":"critical|high|medium|low","confidence":0.0,"reason":"简短中文说明","evidence":["证据1"],"trigger_inspection":true}'
    )
    user_payload = {
        "policy": {
            "source": binding.policy_source,
            "display_name": binding.display_name,
            "rule_text": binding.rule_text,
            "policy_severity_hint": binding.policy_severity_hint,
            "severity_constraint_mode": binding.severity_constraint_mode,
            "severity_warning": binding.severity_warning,
            "analysis_strategy": binding.analysis_strategy,
            "analysis_config": analysis_config,
        },
        "runtime_state": {
            "active": bool(state.is_active),
            "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None,
            "last_decision": state.last_decision,
            "last_confidence": state.last_confidence,
            "last_reason": state.last_reason,
            "last_triggered_at": state.last_triggered_at.isoformat() if state.last_triggered_at else None,
            "last_recovered_at": state.last_recovered_at.isoformat() if state.last_recovered_at else None,
        },
        "feature_summary": feature_summary,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _json_dumps(user_payload)},
    ]


def should_skip_candidate_due_to_interval(
    state: AlertAIRuntimeState,
    gate_decision: AlertAIGateDecision,
    analysis_config: dict[str, Any],
    current_time: datetime,
) -> tuple[bool, str]:
    if not gate_decision.fingerprint:
        return False, ""

    if gate_decision.candidate_type == "recovery":
        min_interval = int(analysis_config.get("active_recovery_min_eval_interval_seconds", 180) or 180)
    elif gate_decision.candidate_type == "backstop":
        min_interval = int(analysis_config.get("active_backstop_eval_seconds", 1800) or 1800)
    else:
        min_interval = int(analysis_config.get("inactive_min_eval_interval_seconds", 300) or 300)

    if (
        state.last_candidate_fingerprint
        and state.last_ai_evaluated_at
        and state.last_candidate_fingerprint == gate_decision.fingerprint
        and (current_time - state.last_ai_evaluated_at).total_seconds() < min_interval
    ):
        return True, "same_candidate_throttled"
    return False, ""


def enforce_policy_severity_constraint(
    judge_result: AlertAIJudgeResult,
    binding: AlertAIPolicyBinding,
) -> AlertAIJudgeResult:
    judge_result.policy_severity_hint = binding.policy_severity_hint

    if binding.severity_constraint_mode == SEVERITY_SOURCE_EXPLICIT and binding.policy_severity_hint:
        if judge_result.severity != binding.policy_severity_hint:
            judge_result.error_message = (
                f"模型返回等级 {judge_result.severity} 与模板显式等级 {binding.policy_severity_hint} 不一致"
            )
            judge_result.reason = f"AI 判警失败：{judge_result.error_message}"
            judge_result.severity_source = SEVERITY_SOURCE_INVALID
            return judge_result

        judge_result.severity_source = SEVERITY_SOURCE_EXPLICIT
        return judge_result

    judge_result.severity_source = SEVERITY_SOURCE_INFERRED
    return judge_result


async def evaluate_alert_ai_policy(
    db: AsyncSession,
    datasource,
    binding: AlertAIPolicyBinding,
    feature_summary: dict[str, Any],
    state: AlertAIRuntimeState,
    *,
    mode: str = "formal",
) -> tuple[AlertAIJudgeResult, AlertAIEvaluationLog]:
    client, model = await resolve_alert_ai_client(db, preferred_model_id=binding.model_id)
    if not client or not model:
        judge_result = AlertAIJudgeResult(
            decision=AI_DECISION_NO_ALERT,
            severity="medium",
            confidence=0.0,
            reason="AI 判警失败：AI 判警模型未配置",
            evidence=[],
            trigger_inspection=False,
            raw_response="",
            severity_source=SEVERITY_SOURCE_INVALID,
            policy_severity_hint=binding.policy_severity_hint,
            error_message="AI 判警模型未配置",
        )
        log_entry = AlertAIEvaluationLog(
            datasource_id=datasource.id,
            policy_id=binding.policy_id,
            policy_source=binding.policy_source,
            policy_fingerprint=binding.policy_fingerprint,
            model_id=None,
            mode=mode,
            decision=judge_result.decision,
            confidence=judge_result.confidence,
            severity=judge_result.severity,
            trigger_inspection=False,
            is_accepted=False,
            error_message=judge_result.error_message,
            reason=judge_result.reason,
            policy_severity_hint=binding.policy_severity_hint,
            severity_source=judge_result.severity_source,
            evidence=judge_result.evidence,
            feature_summary=feature_summary,
            raw_response="",
        )
        db.add(log_entry)
        await db.flush()
        return judge_result, log_entry

    timeout_seconds = await get_ai_alert_timeout_seconds(db)
    messages = _build_alert_ai_messages(binding, feature_summary, state)
    raw_response = ""
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    error_message = None
    started_at = perf_counter()

    try:
        raw_response, usage = await asyncio.wait_for(
            request_text_response_with_usage(
                client,
                messages,
                temperature=0,
                max_tokens=512,
            ),
            timeout=timeout_seconds,
        )
        parsed = _extract_json_from_text(raw_response)
        if parsed is None:
            raise ValueError("模型未返回合法 JSON")
        judge_result = _normalize_judge_result(parsed, raw_response)
        judge_result = enforce_policy_severity_constraint(judge_result, binding)
    except Exception as exc:
        error_message = str(exc)
        judge_result = AlertAIJudgeResult(
            decision=AI_DECISION_NO_ALERT,
            severity="medium",
            confidence=0.0,
            reason=f"AI 判警失败：{error_message}",
            evidence=[],
            trigger_inspection=False,
            raw_response=raw_response,
            severity_source=SEVERITY_SOURCE_INVALID,
            policy_severity_hint=binding.policy_severity_hint,
            error_message=error_message,
        )

    judge_result.prompt_tokens = usage.get("input_tokens", 0)
    judge_result.completion_tokens = usage.get("output_tokens", 0)
    judge_result.total_tokens = usage.get("total_tokens", 0)
    judge_result.latency_ms = int((perf_counter() - started_at) * 1000)
    judge_result.reason = _compress_alert_ai_reason(
        decision=judge_result.decision,
        severity=judge_result.severity,
        reason=judge_result.reason,
    )
    judge_result.evidence = _compress_alert_ai_evidence(judge_result.evidence)

    log_entry = AlertAIEvaluationLog(
        datasource_id=datasource.id,
        policy_id=binding.policy_id,
        policy_source=binding.policy_source,
        policy_fingerprint=binding.policy_fingerprint,
        model_id=model.id,
        mode=mode,
        decision=judge_result.decision,
        confidence=judge_result.confidence,
        severity=judge_result.severity,
        trigger_inspection=judge_result.trigger_inspection,
        is_accepted=False,
        error_message=error_message,
        reason=judge_result.reason,
        policy_severity_hint=binding.policy_severity_hint,
        severity_source=judge_result.severity_source,
        evidence=judge_result.evidence,
        feature_summary=feature_summary,
        raw_response=judge_result.raw_response,
        prompt_tokens=judge_result.prompt_tokens,
        completion_tokens=judge_result.completion_tokens,
        total_tokens=judge_result.total_tokens,
        latency_ms=judge_result.latency_ms,
    )
    db.add(log_entry)
    await db.flush()
    return judge_result, log_entry


async def _find_active_ai_alert(
    db: AsyncSession,
    datasource_id: int,
    display_name: str,
) -> Optional[AlertMessage]:
    result = await db.execute(
        select(AlertMessage)
        .where(
            AlertMessage.datasource_id == datasource_id,
            AlertMessage.alert_type == "ai_policy_violation",
            AlertMessage.metric_name == display_name[:100],
            AlertMessage.status.in_(["active", "acknowledged"]),
        )
        .order_by(AlertMessage.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def apply_alert_ai_result(
    db: AsyncSession,
    datasource,
    binding: AlertAIPolicyBinding,
    state: AlertAIRuntimeState,
    judge_result: AlertAIJudgeResult,
    *,
    inspection_service=None,
    evaluation_log: Optional[AlertAIEvaluationLog] = None,
    mode: str = "formal",
) -> dict[str, Any]:
    current_time = now()
    confidence_threshold = await get_ai_alert_confidence_threshold(db)
    transition = compute_ai_transition(
        active=bool(state.is_active),
        decision=judge_result.decision,
        confidence=judge_result.confidence,
        confidence_threshold=confidence_threshold,
        consecutive_alert_count=state.consecutive_alert_count or 0,
        consecutive_recover_count=state.consecutive_recover_count or 0,
        cooldown_until=state.cooldown_until,
        current_time=current_time,
    )

    action = "noop"
    if mode == "formal" and not judge_result.error_message:
        if transition.action == "trigger_alert":
            trigger_reason = judge_result.reason or "AI 判定命中告警策略"
            alert = await AlertService.create_alert(
                db=db,
                datasource_id=datasource.id,
                alert_type="ai_policy_violation",
                severity=judge_result.severity,
                metric_name=binding.display_name[:100],
                trigger_reason=trigger_reason,
            )
            state.alert_id = alert.id
            state.is_active = True
            state.last_triggered_at = current_time
            action = "trigger_alert"

            if judge_result.trigger_inspection and inspection_service:
                await inspection_service.trigger_inspection(
                    db=db,
                    datasource_id=datasource.id,
                    trigger_type="anomaly",
                    reason=trigger_reason or f"AI 告警策略命中：{binding.display_name}",
                    datasource_metric={
                        "policy": {
                            "policy_id": binding.policy_id,
                            "policy_source": binding.policy_source,
                            "policy_fingerprint": binding.policy_fingerprint,
                            "display_name": binding.display_name,
                        },
                        "decision": {
                            "decision": judge_result.decision,
                            "severity": judge_result.severity,
                            "severity_source": judge_result.severity_source,
                            "policy_severity_hint": judge_result.policy_severity_hint,
                            "confidence": judge_result.confidence,
                            "reason": judge_result.reason,
                            "evidence": judge_result.evidence,
                        },
                    },
                    alert_id=alert.id,
                )

        elif transition.action == "recover_alert":
            alert = None
            if state.alert_id:
                alert = await db.get(AlertMessage, state.alert_id)
            if not alert:
                alert = await _find_active_ai_alert(db, datasource.id, binding.display_name)
            if alert:
                await AlertService.resolve_alert(db, alert.id)
            state.alert_id = None
            state.is_active = False
            state.last_recovered_at = current_time
            action = "recover_alert"

    state.policy_id = binding.policy_id
    state.policy_source = binding.policy_source
    state.policy_fingerprint = binding.policy_fingerprint
    state.is_active = transition.active if mode == "formal" else state.is_active
    state.consecutive_alert_count = transition.consecutive_alert_count if mode == "formal" else state.consecutive_alert_count
    state.consecutive_recover_count = transition.consecutive_recover_count if mode == "formal" else state.consecutive_recover_count
    state.cooldown_until = transition.cooldown_until if mode == "formal" else state.cooldown_until
    state.last_decision = judge_result.decision
    state.last_confidence = judge_result.confidence
    state.last_reason = judge_result.reason
    state.last_evidence = judge_result.evidence
    state.last_evaluated_at = current_time

    # Update event time if alert is active but no action taken (cooldown/confirmation pending)
    if action == "noop" and state.is_active and state.alert_id and mode == "formal":
        from backend.services.alert_event_service import AlertEventService
        try:
            await AlertEventService.update_active_event_time(
                db=db,
                datasource_id=datasource.id,
                alert_type="ai_policy_violation",
                metric_name=binding.display_name[:100]
            )
        except Exception as e:
            logger.warning(f"Failed to update event time for AI alert noop: {e}")

    accepted = action in {"trigger_alert", "recover_alert"}
    if evaluation_log is not None:
        evaluation_log.is_accepted = accepted

    await db.flush()
    return {
        "action": action,
        "accepted": accepted,
        "confidence_threshold": confidence_threshold,
    }


async def get_latest_runtime_state_for_config(
    db: AsyncSession,
    datasource_id: int,
    config,
) -> Optional[AlertAIRuntimeState]:
    binding = await resolve_configured_alert_ai_policy_binding(db, config)
    if not binding:
        return None
    result = await db.execute(
        select(AlertAIRuntimeState).where(
            AlertAIRuntimeState.datasource_id == datasource_id,
            AlertAIRuntimeState.policy_fingerprint == binding.policy_fingerprint,
        )
    )
    return result.scalar_one_or_none()
