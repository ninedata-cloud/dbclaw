import asyncio
import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING, List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, case

from backend.utils.datetime_helper import now

from backend.models.alert_message import AlertMessage
from backend.models.alert_subscription import AlertSubscription
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.schemas.alert import (
    AlertMessageCreate,
    AlertMessageResponse,
    AlertSubscriptionCreate,
    AlertSubscriptionResponse,
    AlertQueryParams,
    IntegrationTarget,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from backend.models.alert_event import AlertEvent

SUMMARY_SECTION_KEYS = ["告警摘要", "诊断摘要", "摘要", "核心结论", "结论概述", "summary"]
ROOT_CAUSE_SECTION_KEYS = ["根本原因", "root cause", "原因分析", "问题原因", "可能原因", "causes", "cause"]
ACTION_SECTION_KEYS = ["处置建议", "修复建议", "建议动作", "建议", "操作建议", "修复步骤", "下一步", "actions", "action"]
PROCESS_MARKERS = [
    "我来分析",
    "让我",
    "现在开始",
    "接下来",
    "制定诊断计划",
    "开始收集证据",
    "获取更多",
    "修正查询",
    "继续分析",
    "现在我已经",
    "让我分析",
    "让我获取",
    "让我们",
    "plan",
    "planning",
]
CONNECTION_FAILURE_PREFIXES = [
    "connection failed:",
    "connection failed",
    "数据库连接失败：",
    "数据库连接失败:",
    "数据库连接失败",
]
GENERIC_AI_POLICY_METRIC_NAMES = {"ai 智能判警", "ai 判警"}
AI_POLICY_FALLBACK_TITLES = {
    "AI 智能判警告警",
    "AI 判警告警",
    "AI 智能判警",
    "AI 判警",
}
METRIC_DISPLAY_LABELS = {
    "connections_active": "活跃连接数",
    "active_connections": "活跃连接数",
    "connection_count": "活跃连接数",
    "threads_running": "活跃连接数",
    "connections_total": "总连接数",
    "total_connections": "总连接数",
    "threads_connected": "总连接数",
}
DEFAULT_EVENT_AI_CONFIG = {
    "enabled": True,
    "trigger_on_create": True,
    "trigger_on_severity_upgrade": True,
    "trigger_on_recovery": False,
    "stale_recheck_minutes": 30,
}


def _strip_markdown_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(r"```[\s\S]*?```", " ", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_~>#]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _normalize_line(line: str) -> str:
    plain = _strip_markdown_text(line)
    plain = re.sub(r"^[\-\*\u2022]+\s*", "", plain)
    plain = re.sub(r"^\d+[\.\)、]\s*", "", plain)
    plain = re.sub(r"^[（(]?\d+[）)]\s*", "", plain)
    return plain.strip(" ：:;；")


def _looks_like_process_line(line: str) -> bool:
    plain = _normalize_line(line).lower()
    if not plain:
        return True
    if plain.startswith(("步骤", "计划", "分析", "诊断")) and ("如下" in plain or "如下：" in plain):
        return True
    return any(marker in plain for marker in PROCESS_MARKERS)


def _extract_sections(full_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if not full_text:
        return sections

    header_pattern = re.compile(r"^#{1,4}\s*(.+?)\s*$", re.MULTILINE)
    parts = header_pattern.split(full_text)
    if len(parts) <= 1:
        return sections

    for index in range(1, len(parts), 2):
        header = parts[index].strip().lower()
        content = parts[index + 1].strip() if index + 1 < len(parts) else ""
        sections[header] = content
    return sections


def _find_section_content(sections: dict[str, str], keys: list[str]) -> Optional[str]:
    for header, content in sections.items():
        if any(key.lower() in header for key in keys):
            return content
    return None


def _extract_keyword_block(full_text: str, keys: list[str]) -> Optional[str]:
    for key in keys:
        pattern = re.compile(
            rf"{re.escape(key)}\s*[：:]\s*(.+?)(?=\n\s*\n|\n#{1,4}\s|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(full_text)
        if match:
            return match.group(1).strip()
    return None


def _clean_section_text(text: Optional[str], *, max_lines: int, max_chars: int) -> Optional[str]:
    if not text:
        return None

    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue
        if _looks_like_process_line(line):
            continue
        lowered = line.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(line)
        if len(lines) >= max_lines:
            break

    if not lines:
        plain = _normalize_line(text)
        if plain and not _looks_like_process_line(plain):
            lines = [plain]

    if not lines:
        return None

    joined = "；".join(lines)
    joined = re.sub(r"[；;]{2,}", "；", joined).strip("；; ")
    if len(joined) > max_chars:
        joined = joined[:max_chars].rstrip("，,；;。.!？? ") + "..."
    return joined or None


def _extract_candidate_sentences(text: str) -> list[str]:
    plain = _strip_markdown_text(text)
    if not plain:
        return []
    parts = re.split(r"[。！？!?；;\n]+", plain)
    return [part.strip(" ，,") for part in parts if part and part.strip(" ，,")]


def _extract_root_cause_sentence(full_text: str) -> Optional[str]:
    if not full_text:
        return None

    direct_patterns = [
        r"根本原因(?:是|为|：|:)\s*(.+?)(?:。|；|!|！|\?|？|$)",
        r"主要原因(?:是|为|：|:)\s*(.+?)(?:。|；|!|！|\?|？|$)",
        r"核心原因(?:是|为|：|:)\s*(.+?)(?:。|；|!|！|\?|？|$)",
        r"原因是\s*(.+?)(?:。|；|!|！|\?|？|$)",
    ]
    for pattern in direct_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            candidate = _clean_section_text(match.group(1), max_lines=1, max_chars=220)
            if candidate:
                return candidate

    priority_keywords = ["根本原因", "原因是", "主要原因", "核心原因", "导致", "瓶颈", "竞争", "过载", "阻塞", "饱和", "异常"]
    for sentence in _extract_candidate_sentences(full_text):
        if _looks_like_process_line(sentence):
            continue
        if any(keyword in sentence for keyword in priority_keywords):
            candidate = _clean_section_text(sentence, max_lines=1, max_chars=220)
            if candidate:
                return candidate

    for sentence in _extract_candidate_sentences(full_text):
        if _looks_like_process_line(sentence):
            continue
        candidate = _clean_section_text(sentence, max_lines=1, max_chars=220)
        if candidate:
            return candidate
    return None


def _extract_action_text(full_text: str) -> Optional[str]:
    if not full_text:
        return None

    action_keywords = ["建议", "应", "需要", "可先", "优先", "排查", "执行", "优化", "调整", "检查"]
    candidates: list[str] = []
    for sentence in _extract_candidate_sentences(full_text):
        if _looks_like_process_line(sentence):
            continue
        if any(keyword in sentence for keyword in action_keywords):
            candidates.append(sentence)
        if len(candidates) >= 3:
            break

    if not candidates:
        return None
    return _clean_section_text("\n".join(candidates), max_lines=3, max_chars=320)


def _compact_summary_text(text: Optional[str], *, max_chars: int = 120) -> Optional[str]:
    if not text:
        return None
    cleaned = _clean_section_text(text, max_lines=2, max_chars=max_chars)
    if not cleaned:
        return None
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip("，,；;。.!？? ") + "..."
    return cleaned


def _display_metric_name(metric_name: Optional[str]) -> Optional[str]:
    normalized = (metric_name or "").strip()
    if not normalized:
        return None
    return METRIC_DISPLAY_LABELS.get(normalized.lower(), normalized)


def _build_metric_semantic_hint(metric_name: Optional[str]) -> Optional[str]:
    normalized = (metric_name or "").strip().lower()
    if normalized in {"connections_active", "active_connections", "connection_count", "threads_running"}:
        return "指标口径说明：connections_active/threads_running 表示活跃连接数（当前执行或待执行的会话），不是最大连接数或总连接上限。"
    if normalized in {"connections_total", "total_connections", "threads_connected"}:
        return "指标口径说明：该指标表示总连接数（已建立会话总量）。"
    return None


def is_connection_status_alert(alert_type: Optional[str], metric_name: Optional[str]) -> bool:
    return (alert_type or "") == "system_error" and (metric_name or "") == "connection_status"


def extract_connection_failure_detail(trigger_reason: Optional[str]) -> Optional[str]:
    reason = (trigger_reason or "").strip()
    if not reason:
        return None

    lowered = reason.lower()
    for prefix in CONNECTION_FAILURE_PREFIXES:
        if lowered.startswith(prefix.lower()):
            trimmed = reason[len(prefix):].strip(" ：:")
            return trimmed or None
    return reason.strip(" ：:") or None


def _is_generic_ai_policy_metric_name(metric_name: Optional[str]) -> bool:
    normalized = (metric_name or "").strip().lower()
    return not normalized or normalized in GENERIC_AI_POLICY_METRIC_NAMES


def _is_generic_ai_policy_title(title: Optional[str]) -> bool:
    normalized = (title or "").strip()
    if not normalized:
        return True
    return normalized in AI_POLICY_FALLBACK_TITLES


def _build_ai_policy_reason_title(trigger_reason: Optional[str]) -> Optional[str]:
    cleaned = _compact_summary_text(trigger_reason, max_chars=72)
    if not cleaned:
        return None

    cleaned = re.sub(r"^(原因|触发原因)\s*[：:]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"[，,；;。\s]*(AI|智能)\s*(判定|判警)(为|出)?(风险较高|存在异常风险|命中告警策略|命中策略|异常).*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"[，,；;。\s]*AI\s*判定\s*(风险较高|存在异常风险|异常|命中告警策略).*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip("，,；;。:： ")
    return cleaned or None


def build_ai_policy_display_metric_name(
    metric_name: Optional[str],
    *,
    trigger_reason: Optional[str] = None,
    fault_domain: Optional[str] = None,
) -> str:
    if not _is_generic_ai_policy_metric_name(metric_name):
        return str(metric_name).strip()

    reason = (trigger_reason or "").lower()
    if any(token in reason for token in ("连接失败", "connection failed", "login failed", "socket", "无法连接", "连通失败")):
        return "连接异常"
    if any(token in reason for token in ("复制", "replication", "lag", "延迟")):
        return "复制异常"

    perf_hits: set[str] = set()
    if any(token in reason for token in ("cpu", "处理器")):
        perf_hits.add("cpu")
    if any(token in reason for token in ("内存", "memory", "buffer")):
        perf_hits.add("memory")
    if any(token in reason for token in ("磁盘", "disk", "i/o", "io", "存储", "tempdb")):
        perf_hits.add("storage")
    if any(token in reason for token in ("连接数", "连接池", "session", "会话", "阻塞", "wait", "死锁", "lock")):
        perf_hits.add("connection")
    if any(token in reason for token in ("qps", "tps", "吞吐", "请求", "慢查询", "事务")):
        perf_hits.add("throughput")

    if len(perf_hits) >= 2:
        return "综合性能异常"
    if "cpu" in perf_hits:
        return "CPU 异常"
    if "memory" in perf_hits:
        return "内存异常"
    if "storage" in perf_hits:
        return "存储异常"
    if "connection" in perf_hits:
        return "连接异常"
    if "throughput" in perf_hits:
        return "吞吐异常"

    domain_labels = {
        "availability": "可用性异常",
        "performance": "性能异常",
        "storage": "存储异常",
        "replication": "复制异常",
        "general": "智能判定异常",
    }
    return domain_labels.get((fault_domain or "").lower(), "智能判定异常")


def build_alert_display_title(
    *,
    alert_type: Optional[str],
    title: Optional[str],
    metric_name: Optional[str],
    trigger_reason: Optional[str],
    fault_domain: Optional[str] = None,
) -> str:
    if (alert_type or "") != "ai_policy_violation":
        return title or "-"

    if not _is_generic_ai_policy_title(title):
        return title or "-"

    reason_title = _build_ai_policy_reason_title(trigger_reason)
    if reason_title:
        return reason_title

    metric_label = build_ai_policy_display_metric_name(
        metric_name,
        trigger_reason=trigger_reason,
        fault_domain=fault_domain,
    )
    return f"{metric_label}告警"


def build_alert_display_metric_name(
    *,
    alert_type: Optional[str],
    metric_name: Optional[str],
    trigger_reason: Optional[str],
    fault_domain: Optional[str] = None,
) -> Optional[str]:
    if (alert_type or "") != "ai_policy_violation":
        return metric_name
    return build_ai_policy_display_metric_name(
        metric_name,
        trigger_reason=trigger_reason,
        fault_domain=fault_domain,
    )


def build_alert_title_and_content(
    *,
    alert_type: str,
    metric_name: Optional[str],
    metric_value: Optional[float],
    threshold_value: Optional[float],
    trigger_reason: Optional[str],
) -> tuple[str, str]:
    metric_display_name = _display_metric_name(metric_name) or metric_name

    if is_connection_status_alert(alert_type, metric_name):
        detail = extract_connection_failure_detail(trigger_reason)
        title = "数据库连接失败"
        content_parts = ["状态：数据库连接失败"]
        if detail:
            content_parts.append(f"错误详情：{detail}")
        return title, "\n".join(content_parts)

    if alert_type == "threshold_violation" and metric_display_name:
        title = f"{metric_display_name} 阈值告警"
    elif alert_type == "baseline_deviation" and metric_display_name:
        title = f"{metric_display_name} 基线偏移告警"
    elif alert_type == "ai_policy_violation":
        title = build_alert_display_title(
            alert_type=alert_type,
            title=None,
            metric_name=metric_name,
            trigger_reason=trigger_reason,
        )
    else:
        title = f"{alert_type.replace('_', ' ').title()}"

    content_parts = []
    if metric_display_name and metric_value is not None:
        content_parts.append(f"指标：{metric_display_name} = {metric_value:.2f}")
    if threshold_value is not None:
        content_parts.append(f"阈值：{threshold_value:.2f}")
    if trigger_reason:
        content_parts.append(f"原因：{trigger_reason}")

    content = "\n".join(content_parts) if content_parts else "告警已触发"
    return title, content


def normalize_alert_diagnosis_fields(
    *,
    root_cause: Optional[str],
    recommended_actions: Optional[str],
    summary: Optional[str],
) -> dict[str, Optional[str]]:
    source_text = summary or ""
    extracted_root = _extract_root_cause_sentence(source_text) if source_text else None
    extracted_actions = _extract_action_text(source_text) if source_text else None

    final_root = _clean_section_text(root_cause or extracted_root, max_lines=3, max_chars=500)
    final_actions = _clean_section_text(recommended_actions or extracted_actions, max_lines=5, max_chars=500)
    final_summary = (
        _compact_summary_text(final_root)
        or _compact_summary_text(summary)
        or _compact_summary_text(extracted_root)
    )

    return {
        "root_cause": final_root,
        "recommended_actions": final_actions,
        "summary": final_summary,
    }


def normalize_event_ai_config(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(DEFAULT_EVENT_AI_CONFIG)
    if not isinstance(config, dict):
        return merged
    for key in ("enabled", "trigger_on_create", "trigger_on_severity_upgrade", "trigger_on_recovery"):
        if key in config:
            merged[key] = bool(config.get(key))
    if config.get("stale_recheck_minutes") is not None:
        merged["stale_recheck_minutes"] = max(5, min(1440, int(config.get("stale_recheck_minutes"))))
    return merged


def should_refresh_event_diagnosis(event, event_ai_config: Optional[dict[str, Any]]) -> bool:
    config = normalize_event_ai_config(event_ai_config)
    if not config.get("enabled", True):
        return False
    if not event:
        return False
    if not getattr(event, "ai_diagnosis_summary", None):
        return True

    trigger_reason = getattr(event, "diagnosis_trigger_reason", None)
    refresh_needed = bool(getattr(event, "is_diagnosis_refresh_needed", False))
    if refresh_needed:
        if trigger_reason == "event_created":
            return bool(config.get("trigger_on_create"))
        if trigger_reason == "severity_escalated":
            return bool(config.get("trigger_on_severity_upgrade"))
        if trigger_reason == "event_recovered":
            return bool(config.get("trigger_on_recovery"))
        return True

    completed_at = getattr(event, "diagnosis_completed_at", None)
    if getattr(event, "status", None) in {"active", "acknowledged"} and completed_at:
        stale_minutes = int(config.get("stale_recheck_minutes") or DEFAULT_EVENT_AI_CONFIG["stale_recheck_minutes"])
        return completed_at <= now() - timedelta(minutes=stale_minutes)
    return False


def mark_event_diagnosis_requested(event) -> None:
    if not event:
        return
    event.last_diagnosis_requested_at = now()


def mark_event_diagnosis_completed(event) -> None:
    if not event:
        return
    event.is_diagnosis_refresh_needed = False
    event.last_diagnosed_severity = getattr(event, "severity", None)
    event.last_diagnosed_alert_count = getattr(event, "alert_count", None)
    event.last_diagnosis_requested_at = now()


async def get_event_ai_config_for_datasource(db: AsyncSession, datasource_id: int) -> dict[str, Any]:
    from backend.models.inspection_config import InspectionConfig
    from backend.services.alert_template_service import resolve_effective_inspection_config

    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()
    effective_config = await resolve_effective_inspection_config(db, config) if config else None
    return normalize_event_ai_config(getattr(effective_config, "event_ai_config", None) if effective_config else None)


def _normalize_prompt_field(value: Any, *, max_chars: int = 320) -> Optional[str]:
    if value is None:
        return None

    text = str(value)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars].rstrip("，,；;。.!？? ") + "..."
    return text


def _format_datasource_prompt(datasource) -> Optional[str]:
    if not datasource:
        return None

    parts: list[str] = []
    name = _normalize_prompt_field(getattr(datasource, "name", None), max_chars=120)
    db_type = _normalize_prompt_field(getattr(datasource, "db_type", None), max_chars=60)
    host = _normalize_prompt_field(getattr(datasource, "host", None), max_chars=120)
    port = getattr(datasource, "port", None)

    if name:
        parts.append(name)
    if db_type:
        parts.append(db_type)
    if host and port:
        parts.append(f"{host}:{port}")
    elif host:
        parts.append(host)

    return " / ".join(parts) or None


def _build_alert_diagnosis_draft(
    event,
    *,
    datasource=None,
    latest_alert=None,
    include_now_suffix: bool = False,
) -> str:
    severity_emoji = "🔴" if event.severity == "critical" else "🟠" if event.severity == "high" else "🟡"

    metric_name = getattr(event, "metric_name", None)
    metric_value = None
    threshold_value = None
    if latest_alert:
        metric_name = getattr(latest_alert, "metric_name", None) or metric_name
        metric_value = getattr(latest_alert, "metric_value", None)
        threshold_value = getattr(latest_alert, "threshold_value", None)

    metric_label = _display_metric_name(metric_name)
    metric_semantic_hint = _build_metric_semantic_hint(metric_name)
    metric_info = "未知"
    if metric_label and metric_value is not None:
        metric_info = f"{metric_label}={metric_value}"
    elif metric_label:
        metric_info = metric_label

    threshold_info = f"阈值：{threshold_value}" if threshold_value is not None else None
    trigger_reason = _normalize_prompt_field(getattr(latest_alert, "trigger_reason", None), max_chars=320)
    alert_content = _normalize_prompt_field(getattr(latest_alert, "content", None), max_chars=320)
    datasource_info = _format_datasource_prompt(datasource)

    if event.event_started_at:
        duration_minutes = max((now() - event.event_started_at).total_seconds() / 60, 0)
        duration_text = f"{duration_minutes:.0f} 分钟"
        if include_now_suffix:
            duration_text = f"{duration_text}（截至目前）"
        first_seen = event.event_started_at.isoformat()
    else:
        duration_text = "未知"
        first_seen = "未知"

    context_lines = [
        f"{severity_emoji} 告警：{event.title}",
        "",
        f"数据库：{datasource_info}" if datasource_info else None,
        f"级别：{event.severity}",
        f"类型：{event.alert_type or '未知'}",
        f"指标：{metric_info}",
        threshold_info,
        metric_semantic_hint,
        f"最近触发原因：{trigger_reason}" if trigger_reason else None,
        f"最近告警内容：{alert_content}" if alert_content else None,
        f"首次时间：{first_seen}",
        f"持续时间：{duration_text}",
        "",
        "这是告警通知场景，请只输出最终结论，不要输出“我来分析/让我/开始收集证据/制定计划”等过程描述。",
        "请分析此告警的根本原因并给出处置建议。请严格按以下格式输出（使用 Markdown）：",
        "",
        "## 告警摘要",
        "<用 1 句话直接说明核心根因，不超过 60 字>",
        "",
        "## 根本原因",
        "- <直接描述告警核心根因，优先写已经证实的原因>",
        "",
        "## 处置建议",
        "- <列出 1-3 条可操作建议>",
        "",
    ]
    return "\n".join(line for line in context_lines if line is not None)


def _build_diagnosis_identity_filters(AlertEvent, current_event) -> list[Any]:
    filters = [
        AlertEvent.datasource_id == current_event.datasource_id,
        AlertEvent.alert_type == current_event.alert_type,
    ]

    metric_name = getattr(current_event, "metric_name", None)
    if metric_name:
        filters.append(AlertEvent.metric_name == metric_name)
    else:
        filters.append(AlertEvent.metric_name.is_(None))

    return filters


async def _load_latest_alert_for_event(db: AsyncSession, alert_event_id: int):
    from backend.models.alert_message import AlertMessage

    result = await db.execute(
        select(AlertMessage)
        .where(AlertMessage.event_id == alert_event_id)
        .order_by(AlertMessage.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


class AlertService:
    """Core alert management service"""

    @staticmethod
    def _status_priority_expr():
        return case(
            (AlertMessage.status == "active", 0),
            (AlertMessage.status == "acknowledged", 1),
            else_=2,
        )

    @staticmethod
    def calculate_severity(percent_over: float) -> str:
        """
        Calculate alert severity based on percentage over threshold.

        Args:
            percent_over: Percentage over threshold (e.g., 25.0 means 25% over)

        Returns:
            Severity level: "critical", "high", "medium", or "low"
        """
        if percent_over > 100:
            return "critical"  # More than double the threshold
        elif percent_over > 50:
            return "high"      # 50-100% over threshold
        elif percent_over > 20:
            return "medium"    # 20-50% over threshold
        else:
            return "low"       # 0-20% over threshold

    @staticmethod
    async def create_alert(
        db: AsyncSession,
        datasource_id: int,
        alert_type: str,
        severity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        trigger_reason: Optional[str] = None
    ) -> AlertMessage:
        """
        Create a new alert message.

        Args:
            db: Database session
            datasource_id: ID of the datasource
            alert_type: Type of alert (threshold_violation, custom_expression, system_error, ai_policy_violation)
            severity: Severity level (critical, high, medium, low)
            metric_name: Name of the metric (optional)
            metric_value: Current metric value (optional)
            threshold_value: Configured threshold (optional)
            trigger_reason: Detailed trigger reason (optional)

        Returns:
            Created AlertMessage instance
        """
        title, content = build_alert_title_and_content(
            alert_type=alert_type,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold_value=threshold_value,
            trigger_reason=trigger_reason,
        )

        alert = AlertMessage(
            datasource_id=datasource_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            content=content,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold_value=threshold_value,
            trigger_reason=trigger_reason,
            status="active",
            created_at=now(),
            updated_at=now()
        )

        db.add(alert)
        await db.commit()
        await db.refresh(alert)

        # Process into event
        from backend.services.alert_event_service import AlertEventService
        event = await AlertEventService.process_new_alert(db, alert)

        # Link alert to event
        alert.event_id = event.id
        await db.commit()
        await db.refresh(alert)

        logger.info(f"Created alert {alert.id}: {title} (severity: {severity}), event {event.id}")
        return alert

    @staticmethod
    async def get_alerts(
        db: AsyncSession,
        params: AlertQueryParams
    ) -> tuple[List[AlertMessage], int]:
        """
        Query alerts with filters.

        Args:
            db: Database session
            params: Query parameters

        Returns:
            Tuple of (alerts list, total count)
        """
        query = select(AlertMessage)
        count_query = select(AlertMessage)

        # Build filters
        filters = []

        if params.datasource_ids:
            filters.append(AlertMessage.datasource_id.in_(params.datasource_ids))

        if params.start_time:
            filters.append(AlertMessage.created_at >= params.start_time)

        if params.end_time:
            filters.append(AlertMessage.created_at <= params.end_time)

        if params.status and params.status != "all":
            filters.append(AlertMessage.status == params.status)

        if params.severity:
            filters.append(AlertMessage.severity == params.severity)

        if params.search:
            search_pattern = f"%{params.search}%"
            filters.append(
                or_(
                    AlertMessage.title.like(search_pattern),
                    AlertMessage.content.like(search_pattern)
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        # Apply ordering and pagination
        query = query.order_by(
            AlertService._status_priority_expr().asc(),
            desc(AlertMessage.created_at),
            desc(AlertMessage.id),
        )
        query = query.limit(params.limit).offset(params.offset)

        result = await db.execute(query)
        alerts = result.scalars().all()

        return alerts, total

    @staticmethod
    async def get_alert_by_id(db: AsyncSession, alert_id: int) -> Optional[AlertMessage]:
        """Get alert by ID"""
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.id == alert_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def acknowledge_alert(
        db: AsyncSession,
        alert_id: int,
        user_id: int
    ) -> Optional[AlertMessage]:
        """
        Mark alert as acknowledged.

        Args:
            db: Database session
            alert_id: Alert ID
            user_id: User who acknowledged the alert

        Returns:
            Updated AlertMessage or None if not found
        """
        alert = await AlertService.get_alert_by_id(db, alert_id)
        if not alert:
            return None

        alert.status = "acknowledged"
        alert.acknowledged_by = user_id
        alert.acknowledged_at = now()
        alert.updated_at = now()

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert {alert_id} acknowledged by user {user_id}")
        return alert

    @staticmethod
    async def resolve_alert(
        db: AsyncSession,
        alert_id: int,
        resolved_value: Optional[float] = None
    ) -> Optional[AlertMessage]:
        """
        Mark alert as resolved.

        Args:
            db: Database session
            alert_id: Alert ID
            resolved_value: Metric value at time of recovery

        Returns:
            Updated AlertMessage or None if not found
        """
        alert = await AlertService.get_alert_by_id(db, alert_id)
        if not alert:
            return None

        alert.status = "resolved"
        alert.resolved_at = now()
        alert.updated_at = now()
        if resolved_value is not None:
            alert.resolved_value = resolved_value

        await db.commit()
        await db.refresh(alert)

        logger.info(f"Alert {alert_id} resolved")

        # Check if parent event should be auto-resolved
        if alert.event_id:
            from backend.services.alert_event_service import AlertEventService
            resolved_event = await AlertEventService.check_and_auto_resolve_event(db, alert.event_id)
            if resolved_event:
                await db.commit()
                logger.info(f"Auto-resolved event {alert.event_id} after all alerts resolved")

        return alert

    @staticmethod
    async def get_all_subscriptions(db: AsyncSession) -> List[AlertSubscription]:
        """Get all active subscriptions"""
        result = await db.execute(
            alive_select(AlertSubscription).where(AlertSubscription.is_enabled == True)
        )
        return result.scalars().all()

    @staticmethod
    async def get_user_subscriptions(
        db: AsyncSession,
        user_id: int
    ) -> List[AlertSubscription]:
        """Get all subscriptions for a user"""
        result = await db.execute(
            alive_select(AlertSubscription).where(AlertSubscription.user_id == user_id)
        )
        return result.scalars().all()

    @staticmethod
    async def create_subscription(
        db: AsyncSession,
        subscription_data: AlertSubscriptionCreate
    ) -> AlertSubscription:
        """Create a new alert subscription"""
        # Convert time_ranges to dict format for JSON storage
        time_ranges_dict = [tr.model_dump() for tr in subscription_data.time_ranges]

        subscription = AlertSubscription(
            user_id=subscription_data.user_id,
            datasource_ids=subscription_data.datasource_ids,
            severity_levels=subscription_data.severity_levels,
            time_ranges=time_ranges_dict,
            integration_targets=[target.model_dump() for target in subscription_data.integration_targets],
            is_enabled=subscription_data.enabled,
            aggregation_script=subscription_data.aggregation_script
        )

        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)

        logger.info(f"Created subscription {subscription.id} for user {subscription_data.user_id}")
        return subscription

    @staticmethod
    async def update_subscription(
        db: AsyncSession,
        subscription_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[AlertSubscription]:
        """Update an alert subscription"""
        subscription = await get_alive_by_id(db, AlertSubscription, subscription_id)

        if not subscription:
            return None

        # Convert time_ranges if present
        if 'time_ranges' in update_data and update_data['time_ranges']:
            update_data['time_ranges'] = [
                tr.model_dump() if hasattr(tr, 'model_dump') else tr
                for tr in update_data['time_ranges']
            ]

        if 'integration_targets' in update_data and update_data['integration_targets'] is not None:
            update_data['integration_targets'] = [
                t.model_dump() if hasattr(t, 'model_dump') else t
                for t in update_data['integration_targets']
            ]

        for key, value in update_data.items():
            if value is not None:
                setattr(subscription, key, value)

        subscription.updated_at = now()

        await db.commit()
        await db.refresh(subscription)

        logger.info(f"Updated subscription {subscription_id}")
        return subscription

    @staticmethod
    async def delete_subscription(
        db: AsyncSession,
        subscription_id: int,
        user_id: int | None = None
    ) -> bool:
        """Soft delete an alert subscription"""
        subscription = await get_alive_by_id(db, AlertSubscription, subscription_id)

        if not subscription:
            return False

        subscription.soft_delete(user_id)
        subscription.updated_at = now()
        await db.commit()

        logger.info(f"Soft deleted subscription {subscription_id}")
        return True

    @staticmethod
    async def get_pending_notifications(
        db: AsyncSession,
        minutes: int = 10
    ) -> List[AlertMessage]:
        """
        Get active alerts that are due for notification.

        Returns active alerts when:
        - notified_at is NULL (never successfully notified), or
        - notified_at is older than the cooldown window.

        Args:
            db: Database session
            minutes: Notification cooldown window

        Returns:
            List of alerts that need notification
        """
        cutoff_time = now() - timedelta(minutes=max(int(minutes or 0), 0))

        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.status == "active",
                    or_(
                        AlertMessage.notified_at.is_(None),
                        AlertMessage.notified_at <= cutoff_time,
                    ),
                )
            )
        )
        return result.scalars().all()

    @staticmethod
    async def get_pending_recovery_notifications(
        db: AsyncSession,
        minutes: int = 60
    ) -> List[AlertMessage]:
        """
        Get recently resolved alerts that need recovery notifications.

        Only returns alerts that have been successfully notified at least once.
        If the original alert was suppressed by aggregation/cooldown and never
        reached any subscription, the recovery notification should also be skipped.

        Args:
            db: Database session
            minutes: Only consider alerts resolved within this window

        Returns:
            List of resolved alerts within the time window
        """
        cutoff_time = now() - timedelta(minutes=minutes)

        # Get recently resolved alerts
        result = await db.execute(
            select(AlertMessage).where(
                and_(
                    AlertMessage.status == "resolved",
                    AlertMessage.resolved_at >= cutoff_time,
                    AlertMessage.notified_at.is_not(None),
                )
            )
        )
        return result.scalars().all()

    @staticmethod
    async def has_alert_notification_for_subscription(
        db: AsyncSession,
        alert_id: int,
        subscription_id: int
    ) -> bool:
        """
        Check if the original alert notification has already been sent for a
        specific alert + subscription combination.

        Recovery notifications should only be sent to subscriptions that
        actually received the original alert.
        """
        delivery_result = await db.execute(
            select(AlertDeliveryLog).where(
                and_(
                    AlertDeliveryLog.alert_id == alert_id,
                    AlertDeliveryLog.subscription_id == subscription_id,
                    AlertDeliveryLog.channel.not_like("%recovery%"),
                    AlertDeliveryLog.status == "sent",
                )
            )
        )
        return delivery_result.scalars().first() is not None

    @staticmethod
    async def has_recovery_notification_for_subscription(
        db: AsyncSession,
        alert_id: int,
        subscription_id: int
    ) -> bool:
        """
        Check if a recovery notification has already been sent for a specific
        alert + subscription combination.

        Args:
            db: Database session
            alert_id: Alert ID
            subscription_id: Subscription ID

        Returns:
            True if recovery notification already sent
        """
        delivery_result = await db.execute(
            select(AlertDeliveryLog).where(
                and_(
                    AlertDeliveryLog.alert_id == alert_id,
                    AlertDeliveryLog.subscription_id == subscription_id,
                    AlertDeliveryLog.channel.like("%recovery%"),
                    AlertDeliveryLog.status == "sent"
                )
            )
        )
        return delivery_result.scalars().first() is not None

    @staticmethod
    async def trigger_auto_diagnosis(db: AsyncSession, alert_event_id: int) -> Optional[str]:
        """
        Trigger AI auto-diagnosis for an alert event and return the diagnosis summary.
        Creates a hidden diagnostic session, runs diagnosis skills, and saves the summary.

        Args:
            db: Database session
            alert_event_id: The alert event ID to diagnose

        Returns:
            AI-generated diagnosis summary string, or None if diagnosis failed
        """
        from backend.models.alert_event import AlertEvent
        from backend.models.diagnostic_session import DiagnosticSession
        from backend.models.datasource import Datasource
        from backend.models.soft_delete import alive_filter

        # Get alert event
        result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_event_id))
        event = result.scalar_one_or_none()
        if not event:
            logger.warning(f"Alert event {alert_event_id} not found for auto-diagnosis")
            return None

        # Skip if diagnosis already completed and no refresh is pending
        if event.diagnosis_status == "completed" and event.ai_diagnosis_summary and not event.is_diagnosis_refresh_needed:
            logger.info(f"Auto-diagnosis skipped for event {alert_event_id}: already completed")
            normalized = normalize_alert_diagnosis_fields(
                root_cause=event.root_cause,
                recommended_actions=event.recommended_actions,
                summary=event.ai_diagnosis_summary,
            )
            return normalized["summary"]

        # Dedup: reuse a recent same-type completed diagnosis if available.
        recent_diagnosis = await _find_recent_diagnosis(db, event)
        if recent_diagnosis:
            logger.info(
                f"Auto-diagnosis: reusing recent diagnosis from event {recent_diagnosis.id} "
                f"for alert event {alert_event_id}"
            )
            await _reuse_diagnosis_from_event(db, event, recent_diagnosis)
            return event.ai_diagnosis_summary

        in_progress_diagnosis = await _find_in_progress_diagnosis(db, event)
        if in_progress_diagnosis:
            logger.info(
                f"Auto-diagnosis skipped for event {alert_event_id}: "
                f"event {in_progress_diagnosis.id} is already diagnosing "
                f"(datasource={event.datasource_id}, type={event.alert_type})"
            )
            event.diagnosis_status = "pending"
            event.diagnosis_source_event_id = in_progress_diagnosis.id
            await db.commit()
            return f"同类告警正在诊断中（事件 {in_progress_diagnosis.id}）..."

        # Get datasource
        result = await db.execute(select(Datasource).where(Datasource.id == event.datasource_id, alive_filter(Datasource)))
        ds = result.scalar_one_or_none()
        if not ds:
            logger.warning(f"Datasource {event.datasource_id} not found for auto-diagnosis")
            return None

        latest_alert = await _load_latest_alert_for_event(db, alert_event_id)

        event.diagnosis_status = "in_progress"
        event.diagnosis_started_at = now()
        event.diagnosis_completed_at = None
        event.diagnosis_source_event_id = None
        mark_event_diagnosis_requested(event)
        await db.commit()

        draft = _build_alert_diagnosis_draft(
            event,
            datasource=ds,
            latest_alert=latest_alert,
            include_now_suffix=True,
        )

        # Create hidden diagnostic session
        session = DiagnosticSession(
            datasource_id=event.datasource_id,
            user_id=None,  # System session
            title=f"自动诊断: {event.title[:40]}",
            is_hidden=True,  # Hidden from user session list
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.info(f"Created auto-diagnosis session {session.id} for alert event {alert_event_id}")

        # Run AI diagnosis asynchronously (non-blocking)
        # The diagnosis will update the alert_event.ai_diagnosis_summary field
        asyncio.create_task(_run_auto_diagnosis(session.id, alert_event_id, ds.id, ds.db_type, draft))

        return f"正在诊断中（会话 {session.id}）..."


async def _run_auto_diagnosis(session_id: int, alert_event_id: int, datasource_id: int, db_type: str, draft: str):
    """
    Run auto-diagnosis for a given session (background, non-blocking).
    Reuses _run_diagnosis_coro and saves extracted structured results.
    """
    from backend.models.alert_event import AlertEvent
    from backend.database import async_session as db_session_factory

    try:
        diagnosis_text = await _run_diagnosis_coro(session_id, alert_event_id, datasource_id, db_type, draft)

        if diagnosis_text:
            async with db_session_factory() as db:
                from sqlalchemy import update
                root_cause, recommended_actions, summary = _extract_diagnosis_parts(diagnosis_text)
                await db.execute(
                    update(AlertEvent)
                    .where(AlertEvent.id == alert_event_id)
                    .values(
                        ai_diagnosis_summary=summary,
                        root_cause=root_cause,
                        recommended_actions=recommended_actions,
                        diagnosis_status="completed",
                        diagnosis_completed_at=now(),
                        diagnosis_source_event_id=None,
                        is_diagnosis_refresh_needed=False,
                        last_diagnosed_severity=select(AlertEvent.severity).where(AlertEvent.id == alert_event_id).scalar_subquery(),
                        last_diagnosed_alert_count=select(AlertEvent.alert_count).where(AlertEvent.id == alert_event_id).scalar_subquery(),
                        last_diagnosis_requested_at=now(),
                    )
                )
                await db.commit()
                logger.info(f"Auto-diagnosis complete for alert event {alert_event_id}: {diagnosis_text[:100]}...")
        else:
            logger.warning(f"Auto-diagnosis returned empty result for alert event {alert_event_id}")
    except Exception as e:
        logger.error(f"Auto-diagnosis failed for alert event {alert_event_id}: {e}", exc_info=True)
        async with db_session_factory() as db:
            from sqlalchemy import update
            await db.execute(
                update(AlertEvent)
                .where(AlertEvent.id == alert_event_id)
                .values(diagnosis_status="failed")
            )
            await db.commit()


def _extract_diagnosis_parts(full_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse AI diagnosis text to extract root_cause, recommended_actions, and summary.

    Returns:
        (root_cause, recommended_actions, summary)
    """
    if not full_text:
        return None, None, None

    sections = _extract_sections(full_text)

    summary_section = _find_section_content(sections, SUMMARY_SECTION_KEYS) or _extract_keyword_block(full_text, SUMMARY_SECTION_KEYS)
    root_cause_section = _find_section_content(sections, ROOT_CAUSE_SECTION_KEYS) or _extract_keyword_block(full_text, ROOT_CAUSE_SECTION_KEYS)
    action_section = _find_section_content(sections, ACTION_SECTION_KEYS) or _extract_keyword_block(full_text, ACTION_SECTION_KEYS)

    root_cause = _clean_section_text(root_cause_section, max_lines=3, max_chars=500) or _extract_root_cause_sentence(full_text)
    recommended_actions = _clean_section_text(action_section, max_lines=5, max_chars=500) or _extract_action_text(full_text)
    summary = (
        _compact_summary_text(summary_section)
        or _compact_summary_text(root_cause)
        or _compact_summary_text(_extract_root_cause_sentence(full_text))
    )

    return root_cause, recommended_actions, summary


async def _get_diagnosis_dedup_window_minutes(db: AsyncSession) -> int:
    """Load diagnosis dedup window from system config."""
    from backend.services.config_service import get_config
    from backend.config import get_settings

    dedup_minutes = await get_config(
        db, "inspection_dedup_window_minutes",
        default=get_settings().inspection_dedup_window_minutes
    )
    if not dedup_minutes:
        return 0
    return int(dedup_minutes)


async def _reuse_diagnosis_from_event(db: AsyncSession, current_event, source_event) -> None:
    """Copy diagnosis result from a recent same-type event."""
    normalized = normalize_alert_diagnosis_fields(
        root_cause=source_event.root_cause,
        recommended_actions=source_event.recommended_actions,
        summary=source_event.ai_diagnosis_summary,
    )
    current_event.ai_diagnosis_summary = normalized["summary"]
    current_event.root_cause = normalized["root_cause"]
    current_event.recommended_actions = normalized["recommended_actions"]
    current_event.diagnosis_status = "completed"
    current_event.diagnosis_completed_at = source_event.diagnosis_completed_at or now()
    current_event.diagnosis_source_event_id = source_event.id
    mark_event_diagnosis_completed(current_event)
    await db.commit()


async def _find_recent_diagnosis(db: AsyncSession, current_event) -> Optional["AlertEvent"]:
    """
    Check if there's a recently completed diagnosis for the same alert identity
    within the inspection_dedup_window_minutes window.

    Returns the recent AlertEvent with completed diagnosis, or None.
    """
    from backend.models.alert_event import AlertEvent

    dedup_minutes = await _get_diagnosis_dedup_window_minutes(db)
    if not dedup_minutes or dedup_minutes <= 0:
        return None

    time_threshold = now() - timedelta(minutes=int(dedup_minutes))

    if not current_event.alert_type:
        return None

    # Build query: same datasource + alert_type + metric_name, completed diagnosis, within window
    filters = [
        AlertEvent.id != current_event.id,
        *_build_diagnosis_identity_filters(AlertEvent, current_event),
        AlertEvent.diagnosis_status == "completed",
        AlertEvent.ai_diagnosis_summary.isnot(None),
        AlertEvent.diagnosis_completed_at.isnot(None),
        AlertEvent.diagnosis_completed_at >= time_threshold,
    ]

    result = await db.execute(
        select(AlertEvent)
        .where(and_(*filters))
        .order_by(AlertEvent.diagnosis_completed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_in_progress_diagnosis(db: AsyncSession, current_event) -> Optional["AlertEvent"]:
    """
    Check if a same-identity diagnosis is already running or pending in the dedup window.
    """
    from backend.models.alert_event import AlertEvent

    dedup_minutes = await _get_diagnosis_dedup_window_minutes(db)
    if not dedup_minutes or dedup_minutes <= 0 or not current_event.alert_type:
        return None

    time_threshold = now() - timedelta(minutes=int(dedup_minutes))

    result = await db.execute(
        select(AlertEvent)
        .where(
            and_(
                AlertEvent.id != current_event.id,
                *_build_diagnosis_identity_filters(AlertEvent, current_event),
                AlertEvent.diagnosis_status.in_(["in_progress", "pending"]),
                AlertEvent.diagnosis_started_at.isnot(None),
                AlertEvent.diagnosis_started_at >= time_threshold,
            )
        )
        .order_by(AlertEvent.diagnosis_started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def run_sync_diagnosis(
    db: AsyncSession,
    alert_event_id: int,
    timeout_seconds: int = 600
) -> Dict[str, Any]:
    """
    Perform synchronous AI diagnosis for an alert event with timeout control.
    Creates a diagnostic session, runs AI analysis, extracts root cause and
    recommended actions, and saves results to the alert event.

    Args:
        db: Database session
        alert_event_id: The alert event ID to diagnose
        timeout_seconds: Maximum time to wait for diagnosis (default 60s)

    Returns:
        Dict with keys: root_cause, recommended_actions, summary, status
    """
    from backend.models.alert_event import AlertEvent
    from backend.models.diagnostic_session import DiagnosticSession
    from backend.models.datasource import Datasource

    # Get alert event
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_event_id))
    event = result.scalar_one_or_none()
    if not event:
        logger.warning(f"Alert event {alert_event_id} not found for sync diagnosis")
        return {"root_cause": None, "recommended_actions": None, "summary": None, "status": "failed"}

    # If diagnosis already completed and this event has not reached a refresh point, return cached result
    if event.diagnosis_status == "completed" and event.ai_diagnosis_summary and not event.is_diagnosis_refresh_needed:
        logger.info(f"Using cached diagnosis for alert event {alert_event_id}")
        normalized = normalize_alert_diagnosis_fields(
            root_cause=event.root_cause,
            recommended_actions=event.recommended_actions,
            summary=event.ai_diagnosis_summary,
        )
        return {
            "root_cause": normalized["root_cause"],
            "recommended_actions": normalized["recommended_actions"],
            "summary": normalized["summary"],
            "status": "completed",
        }

    # Dedup: reuse a recent same-type completed diagnosis if available.
    recent_diagnosis = await _find_recent_diagnosis(db, event)
    if recent_diagnosis:
        logger.info(
            f"Reusing recent diagnosis from event {recent_diagnosis.id} for alert event {alert_event_id} "
            f"(datasource={event.datasource_id}, type={event.alert_type})"
        )
        await _reuse_diagnosis_from_event(db, event, recent_diagnosis)
        normalized = normalize_alert_diagnosis_fields(
            root_cause=recent_diagnosis.root_cause,
            recommended_actions=recent_diagnosis.recommended_actions,
            summary=recent_diagnosis.ai_diagnosis_summary,
        )
        return {
            "root_cause": normalized["root_cause"],
            "recommended_actions": normalized["recommended_actions"],
            "summary": normalized["summary"],
            "status": "completed",
        }

    in_progress_diagnosis = await _find_in_progress_diagnosis(db, event)
    if in_progress_diagnosis:
        logger.info(
            f"Skipping sync diagnosis for event {alert_event_id}: "
            f"event {in_progress_diagnosis.id} is already diagnosing "
            f"(datasource={event.datasource_id}, type={event.alert_type})"
        )
        event.diagnosis_status = "pending"
        event.diagnosis_source_event_id = in_progress_diagnosis.id
        await db.commit()
        return {
            "root_cause": None,
            "recommended_actions": None,
            "summary": f"同类告警正在诊断中，复用事件 {in_progress_diagnosis.id} 的诊断结果...",
            "status": "pending",
        }

    # Get datasource
    result = await db.execute(select(Datasource).where(Datasource.id == event.datasource_id, alive_filter(Datasource)))
    ds = result.scalar_one_or_none()
    if not ds:
        logger.warning(f"Datasource {event.datasource_id} not found for sync diagnosis")
        return {"root_cause": None, "recommended_actions": None, "summary": None, "status": "failed"}

    latest_alert = await _load_latest_alert_for_event(db, alert_event_id)

    # Update status to in_progress
    event.diagnosis_status = "in_progress"
    event.diagnosis_started_at = now()
    event.diagnosis_completed_at = None
    event.diagnosis_source_event_id = None
    mark_event_diagnosis_requested(event)
    await db.commit()

    draft = _build_alert_diagnosis_draft(
        event,
        datasource=ds,
        latest_alert=latest_alert,
    )

    # Create hidden diagnostic session
    session = DiagnosticSession(
        datasource_id=event.datasource_id,
        user_id=None,
        title=f"告警诊断: {event.title[:40]}",
        is_hidden=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(f"Running sync diagnosis for alert event {alert_event_id}, session {session.id}")

    try:
        # Run diagnosis with timeout
        diagnosis_text = await asyncio.wait_for(
            _run_diagnosis_coro(session.id, alert_event_id, ds.id, ds.db_type, draft),
            timeout=timeout_seconds,
        )

        # Extract structured parts
        root_cause, recommended_actions, summary = _extract_diagnosis_parts(diagnosis_text)

        # Save all fields to alert event
        event.ai_diagnosis_summary = summary
        event.root_cause = root_cause
        event.recommended_actions = recommended_actions
        event.diagnosis_status = "completed"
        event.diagnosis_completed_at = now()
        mark_event_diagnosis_completed(event)
        await db.commit()

        logger.info(f"Sync diagnosis complete for alert event {alert_event_id}")
        return {
            "root_cause": root_cause,
            "recommended_actions": recommended_actions,
            "summary": summary,
            "status": "completed",
        }

    except asyncio.TimeoutError:
        logger.warning(f"Sync diagnosis timed out after {timeout_seconds}s for alert event {alert_event_id}")
        event.diagnosis_status = "pending"
        await db.commit()
        return {
            "root_cause": None,
            "recommended_actions": None,
            "summary": "诊断超时，正在后台继续分析...",
            "status": "pending",
        }
    except Exception as e:
        logger.error(f"Sync diagnosis failed for alert event {alert_event_id}: {e}", exc_info=True)
        event.diagnosis_status = "failed"
        await db.commit()
        return {
            "root_cause": None,
            "recommended_actions": None,
            "summary": f"诊断失败: {str(e)[:200]}",
            "status": "failed",
        }


async def _run_diagnosis_coro(
    session_id: int,
    alert_event_id: int,
    datasource_id: int,
    db_type: str,
    draft: str,
) -> str:
    """
    Core async coroutine to run AI diagnosis and return the full text.
    Used by both sync and async diagnosis paths.
    """
    from backend.database import async_session as db_session_factory
    from backend.agent.conversation_skills import run_conversation_with_skills
    from backend.services.knowledge_router import build_knowledge_context
    from backend.models.alert_event import AlertEvent
    from backend.services.chat_orchestration_service import prepare_user_turn
    from sqlalchemy import select
    from backend.models.diagnostic_session import ChatMessage

    async with db_session_factory() as db:
        # Save user message first
        await prepare_user_turn(db, session_id=session_id, user_id=None, user_message=draft)

        # Build messages for AI
        result = await db.execute(
            alive_select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        )
        all_msgs = result.scalars().all()

        messages = []
        for m in all_msgs:
            if m.role == "user":
                messages.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                messages.append({"role": "assistant", "content": m.content})
            elif m.role == "tool_call":
                import json as json_module
                try:
                    data = json_module.loads(m.content)
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": data.get("tool_call_id") or f"call_{data['tool_name']}_{m.id}",
                            "type": "function",
                            "function": {"name": data["tool_name"], "arguments": json_module.dumps(data["tool_args"])}
                        }]
                    })
                except Exception:
                    pass

        # Run conversation (non-streaming, collect final response)
        full_diagnosis = ""
        knowledge_context = await build_knowledge_context(
            db,
            datasource_id=datasource_id,
            user_message=draft,
        )
        async for event in run_conversation_with_skills(
            messages=messages,
            datasource_id=datasource_id,
            model_id=None,
            kb_ids=None,
            knowledge_context=knowledge_context,
            db=db,
            user_id=None,
            session_id=session_id,
            skill_authorizations=None,
        ):
            event_type = event.get("type")
            if event_type == "content":
                full_diagnosis += event["content"]
            elif event_type == "done":
                break
            elif event_type == "error":
                break

        return full_diagnosis
