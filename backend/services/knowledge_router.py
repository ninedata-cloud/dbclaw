from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.diagnosis_context import build_diagnostic_brief
from backend.agent.intent_detector import analyze_query_intent
from backend.models.datasource import Datasource
from backend.models.document import DocCategory, DocDocument
from backend.models.soft_delete import alive_filter
from backend.services.document_service import ensure_document_compiled
from backend.services.knowledge_compiler import build_default_stop_conditions, normalize_diagnosis_profile


ISSUE_KEYWORDS: dict[str, list[str]] = {
    "performance": ["慢", "性能", "cpu", "负载", "卡", "吞吐", "qps", "tps", "高负载", "响应慢"],
    "connectivity": ["连接", "连不上", "timeout", "认证", "拒绝", "connection"],
    "locking": ["锁", "阻塞", "死锁", "等待", "metadata lock", "lock"],
    "replication": ["复制", "主从", "延迟", "同步", "replica", "slave", "standby"],
    "capacity": ["空间", "磁盘", "容量", "表空间", "满", "增长"],
    "sql": ["sql", "查询", "索引", "执行计划", "explain", "慢查询"],
    "resource": ["内存", "iowait", "磁盘io", "network", "网络", "主机", "cpu"],
    "configuration": ["配置", "参数", "变量", "buffer", "max_connections"],
    "error": ["报错", "错误", "异常", "失败", "error", "crash"],
    "general": ["诊断", "巡检", "检查", "分析"],
}

HOST_SKILL_PREFIXES = ("get_os_metrics", "diagnose_", "execute_os_command")
DB_TYPE_COMPATIBILITY = {
    "mysql": ["mysql", "general"],
    "tdsql-c-mysql": ["tdsql-c-mysql", "mysql", "general"],
    "postgresql": ["postgresql", "general"],
    "oracle": ["oracle", "general"],
    "sqlserver": ["sqlserver", "general"],
    "opengauss": ["opengauss", "postgresql", "general"],
    "hana": ["hana", "general"],
}


def infer_issue_categories_from_text(text: str, issue_category: Optional[str] = None) -> list[str]:
    categories: list[str] = []
    if issue_category:
        categories.append(issue_category)
    lowered = (text or "").lower()
    for category, keywords in ISSUE_KEYWORDS.items():
        if category in categories:
            continue
        if any(keyword.lower() in lowered for keyword in keywords):
            categories.append(category)
    if not categories:
        categories.append("general")
    return categories


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_normalize_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_normalize_text(item) for item in value.values())
    return str(value).lower()


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _tokenize_text(text: str) -> list[str]:
    return [
        token
        for token in re.split(r"[\s,，。:：;；/\\()（）\[\]<>\"'`]+", (text or "").lower())
        if len(token) >= 2
    ]


def _compatibility_db_types(db_type: Optional[str]) -> list[str]:
    if not db_type:
        return ["general"]
    return DB_TYPE_COMPATIBILITY.get(db_type.lower(), [db_type.lower(), "general"])


def _needs_host(unit: dict[str, Any]) -> bool:
    for skill_id in unit.get("recommended_skills") or []:
        if any(str(skill_id).startswith(prefix) for prefix in HOST_SKILL_PREFIXES):
            return True
    return False


def _summarize_result(result: Any) -> str:
    parsed = result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except Exception:
            return result[:220]
    if isinstance(parsed, dict):
        if parsed.get("error"):
            return str(parsed.get("error"))[:220]
        compact = []
        for key, value in parsed.items():
            if isinstance(value, (str, int, float, bool)):
                compact.append(f"{key}={value}")
            elif isinstance(value, list):
                compact.append(f"{key}={len(value)}项")
            elif isinstance(value, dict):
                compact.append(f"{key}=对象")
            if len(compact) >= 4:
                break
        return "；".join(compact)[:220]
    if isinstance(parsed, list):
        return f"{len(parsed)} 项结果"
    return str(parsed)[:220]


def _match_tokens_score(text_blob: str, tokens: list[str], cap: int = 20) -> tuple[int, int]:
    hits = sum(1 for token in tokens[:16] if token and token in text_blob)
    return min(hits * 4, cap), hits


def compute_document_route(
    *,
    doc: dict[str, Any],
    user_message: str,
    datasource_id: Optional[int],
    host_id: Optional[int],
    db_type: Optional[str],
    issue_categories: list[str],
    diagnostic_brief: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    route_db_types = _compatibility_db_types(db_type)
    doc_db_types = [item.lower() for item in _ensure_list(doc.get("db_types")) if item]
    if route_db_types and doc_db_types:
        matched_db_type = next((item for item in route_db_types if item in doc_db_types), None)
        if matched_db_type:
            if matched_db_type == db_type:
                score += 30
                reasons.append(f"匹配数据库类型 {db_type}")
            else:
                score += 18
                reasons.append(f"兼容数据库知识 {matched_db_type}")
        elif "general" not in doc_db_types:
            score -= 15
    elif db_type and _normalize_text(doc.get("category_db_type")) in route_db_types:
        score += 20
        reasons.append(f"匹配分类数据库类型 {doc.get('category_db_type')}")

    doc_datasource_ids = [int(item) for item in _ensure_list(doc.get("datasource_ids")) if str(item).isdigit()]
    if datasource_id and doc_datasource_ids:
        if datasource_id in doc_datasource_ids:
            score += 60
            reasons.append("绑定当前数据源")
        else:
            score -= 40

    doc_host_ids = [int(item) for item in _ensure_list(doc.get("host_ids")) if str(item).isdigit()]
    if host_id and doc_host_ids:
        if host_id in doc_host_ids:
            score += 40
            reasons.append("绑定当前主机")
        else:
            score -= 20

    if (doc.get("scope") or "builtin") == "tenant":
        score += 25
        reasons.append("私有运维知识优先")

    doc_issue_categories = [item.lower() for item in _ensure_list(doc.get("issue_categories")) if item]
    matched_issue_categories = [item for item in issue_categories if item.lower() in doc_issue_categories]
    if matched_issue_categories:
        score += 35
        reasons.append(f"匹配问题类别 {matched_issue_categories[0]}")
    elif doc_issue_categories and "general" not in doc_issue_categories:
        score -= 10

    diagnosis_profile = normalize_diagnosis_profile(doc.get("diagnosis_profile"))
    symptom_tags = [item.lower() for item in diagnosis_profile.get("symptom_tags") or []]
    signal_tags = [item.lower() for item in diagnosis_profile.get("signal_tags") or []]
    user_text = _normalize_text(user_message)
    if symptom_tags and any(tag in user_text for tag in symptom_tags):
        score += 18
        reasons.append("命中文档症状标签")
    if signal_tags and any(tag in user_text for tag in signal_tags):
        score += 12
        reasons.append("命中文档信号标签")

    if diagnosis_profile.get("recommended_skills"):
        score += min(len(diagnosis_profile["recommended_skills"]) * 2, 10)

    doc_kind = (doc.get("doc_kind") or "").lower()
    if doc_kind in {"runbook", "known_issue", "case", "sop"}:
        score += 12
        reasons.append(f"{doc_kind} 类型知识更适合诊断")
    elif doc_kind == "reference":
        score -= 5

    freshness = (doc.get("freshness_level") or "stable").lower()
    if freshness == "stable":
        score += 8
    elif freshness == "needs_review":
        score -= 5
    elif freshness == "expired":
        score -= 100

    quality_status = (doc.get("quality_status") or "").lower()
    if quality_status == "ready":
        score += 10
    elif quality_status == "warning":
        score -= 4
    elif quality_status == "expired":
        score -= 50

    text_blob = " ".join(
        [
            _normalize_text(doc.get("title")),
            _normalize_text(doc.get("summary")),
            _normalize_text(doc.get("tags")),
            _normalize_text(doc.get("category_name")),
            _normalize_text(diagnosis_profile.get("symptom_tags")),
            _normalize_text(diagnosis_profile.get("signal_tags")),
        ]
    )
    for category in issue_categories:
        if category.lower() in text_blob:
            score += 8
            reasons.append(f"标题/摘要命中 {category}")
            break

    tokens = _tokenize_text(user_message)
    token_score, keyword_hits = _match_tokens_score(text_blob, tokens)
    score += token_score
    if keyword_hits:
        reasons.append(f"命中 {keyword_hits} 个问题关键词")

    if diagnostic_brief:
        brief_blob = _normalize_text(
            [
                diagnostic_brief.get("triage_summary"),
                diagnostic_brief.get("focus_areas"),
                diagnostic_brief.get("abnormal_signals"),
                diagnostic_brief.get("user_symptoms"),
                diagnostic_brief.get("active_alerts"),
            ]
        )
        if symptom_tags and any(tag in brief_blob for tag in symptom_tags):
            score += 12
            reasons.append("匹配预诊断症状")
        if signal_tags and any(tag in brief_blob for tag in signal_tags):
            score += 10
            reasons.append("匹配预诊断异常信号")

    score += int(doc.get("priority") or 0) * 3
    return {
        "score": score,
        "reasons": _dedupe_preserve_order(reasons),
    }


def _build_route_reason_map(routed_docs: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        str(item.get("document_id")): item.get("reasons") or []
        for item in routed_docs
        if item.get("document_id") is not None
    }


def _score_unit(
    unit: dict[str, Any],
    *,
    doc_score: int,
    issue_categories: list[str],
    user_message: str,
    evidence_ledger: Optional[dict[str, Any]],
    host_configured: bool,
) -> tuple[int, list[str]]:
    score = max(doc_score // 2, 0)
    reasons: list[str] = []
    unit_type = str(unit.get("unit_type") or "citation")
    if unit_type == "trigger":
        score += 18
        reasons.append("触发条件适合首轮筛查")
    elif unit_type == "evidence_step":
        score += 14
        reasons.append("适合作为证据收集步骤")
    elif unit_type == "decision_rule":
        score += 12
        reasons.append("包含判定规则")
    elif unit_type == "action":
        score += 8
        reasons.append("可支持后续建议动作")
    elif unit_type == "risk":
        score += 6
        reasons.append("可补充风险提示")

    if _needs_host(unit) and not host_configured:
        return -100, ["当前数据源未配置主机，跳过 OS 知识单元"]

    text_blob = " ".join(
        [
            _normalize_text(unit.get("title")),
            _normalize_text(unit.get("summary")),
            _normalize_text(unit.get("signal_tags")),
            _normalize_text(unit.get("symptom_tags")),
            _normalize_text(unit.get("body_excerpt")),
        ]
    )
    tokens = _tokenize_text(user_message)
    token_score, keyword_hits = _match_tokens_score(text_blob, tokens, cap=16)
    score += token_score
    if keyword_hits:
        reasons.append(f"命中 {keyword_hits} 个用户关键词")

    for category in issue_categories:
        if category.lower() in text_blob:
            score += 8
            reasons.append(f"单元匹配问题类别 {category}")
            break

    recommended_skills = unit.get("recommended_skills") or []
    if recommended_skills:
        score += min(len(recommended_skills) * 4, 12)
        reasons.append("包含推荐技能")

    if evidence_ledger:
        tool_calls = evidence_ledger.get("tool_calls") or []
        executed_tools = {item.get("tool_name") for item in tool_calls if item.get("success")}
        if executed_tools:
            if unit_type in {"decision_rule", "action", "risk"} and executed_tools.intersection(recommended_skills):
                score += 18
                reasons.append("已有相关工具证据，可用于下一步判定")
            elif unit_type == "evidence_step":
                pending_skills = [skill_id for skill_id in recommended_skills if skill_id not in executed_tools]
                if pending_skills:
                    score += 8
                    reasons.append("推荐技能尚未执行，适合作为下一步")
        consumed_unit_ids = set(evidence_ledger.get("consumed_unit_ids") or [])
        if unit.get("unit_id") in consumed_unit_ids:
            score -= 80
    return score, _dedupe_preserve_order(reasons)


def _build_hypotheses(active_units: list[dict[str, Any]]) -> list[str]:
    hypotheses: list[str] = []
    for unit in active_units:
        unit_type = unit.get("unit_type")
        title = unit.get("title")
        summary = unit.get("summary")
        if unit_type in {"trigger", "decision_rule", "action"}:
            if title and summary:
                hypotheses.append(f"{title}：{summary}")
            elif title:
                hypotheses.append(str(title))
    return _dedupe_preserve_order(hypotheses)[:6]


def activate_units(
    routed_docs: list[dict[str, Any]],
    *,
    issue_categories: list[str],
    user_message: str,
    host_configured: bool,
    evidence_ledger: Optional[dict[str, Any]] = None,
    unit_limit: int = 15,
) -> dict[str, Any]:
    scored_units: list[dict[str, Any]] = []
    route_reason_map = _build_route_reason_map(routed_docs)

    for doc in routed_docs:
        compiled_snapshot = doc.get("compiled_snapshot") or {}
        units = compiled_snapshot.get("units") if isinstance(compiled_snapshot, dict) else []
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            score, reasons = _score_unit(
                unit,
                doc_score=int(doc.get("score") or 0),
                issue_categories=issue_categories,
                user_message=user_message,
                evidence_ledger=evidence_ledger,
                host_configured=host_configured,
            )
            if score < 0:
                continue
            scored_units.append(
                {
                    "unit_id": unit.get("unit_id"),
                    "document_id": doc.get("document_id"),
                    "document_title": doc.get("title"),
                    "node_title": unit.get("title"),
                    "path": unit.get("path"),
                    "unit_type": unit.get("unit_type"),
                    "summary": unit.get("summary"),
                    "recommended_skills": unit.get("recommended_skills") or [],
                    "citation": f"{doc.get('title')} / {unit.get('title')}",
                    "score": score,
                    "reasons": _dedupe_preserve_order(reasons + route_reason_map.get(str(doc.get("document_id")), [])[:2]),
                }
            )

    scored_units.sort(key=lambda item: (-item["score"], item["document_title"] or "", item["node_title"] or ""))
    active_units = scored_units[:unit_limit]
    active_doc_ids = {item["document_id"] for item in active_units if item.get("document_id") is not None}
    active_documents = [
        {
            key: value
            for key, value in doc.items()
            if key
            in {
                "document_id",
                "title",
                "summary",
                "category_name",
                "db_type",
                "scope",
                "doc_kind",
                "score",
                "reason",
                "reasons",
                "quality_status",
                "diagnosis_profile",
                "compiled_snapshot_summary",
            }
        }
        for doc in routed_docs
        if doc.get("document_id") in active_doc_ids
    ]
    recommended_skills = _dedupe_preserve_order(
        [skill_id for item in active_units for skill_id in (item.get("recommended_skills") or [])]
    )[:8]
    merged_profile = normalize_diagnosis_profile(
        {
            "evidence_requirements": [
                requirement
                for doc in routed_docs
                for requirement in (normalize_diagnosis_profile(doc.get("diagnosis_profile")).get("evidence_requirements") or [])
            ]
        }
    )
    citations = _dedupe_preserve_order([item["citation"] for item in active_units if item.get("citation")])
    stop_conditions = build_default_stop_conditions(active_units, merged_profile)
    return {
        "active_documents": active_documents[:5],
        "active_units": active_units,
        "hypotheses": _build_hypotheses(active_units),
        "recommended_skills": recommended_skills,
        "stop_conditions": stop_conditions,
        "citations": citations[:12],
        "route_reasons": {
            str(doc.get("document_id")): doc.get("reasons") or []
            for doc in active_documents
            if doc.get("document_id") is not None
        },
    }


def _build_version_hash(routed_docs: list[dict[str, Any]]) -> str:
    payload = [
        {
            "document_id": item.get("document_id"),
            "title": item.get("title"),
            "compiled_hash": ((item.get("compiled_snapshot") or {}).get("version_hash") if isinstance(item.get("compiled_snapshot"), dict) else None),
        }
        for item in routed_docs
    ]
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def route_playbooks(
    routed_docs: list[dict[str, Any]],
    *,
    unit_limit: int,
    user_message: str,
    issue_categories: list[str],
    host_configured: bool,
    evidence_ledger: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    knowledge_plan = activate_units(
        routed_docs,
        issue_categories=issue_categories,
        user_message=user_message,
        host_configured=host_configured,
        evidence_ledger=evidence_ledger,
        unit_limit=unit_limit,
    )
    return {
        "version": "knowledge-plan/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "version_hash": _build_version_hash(routed_docs),
        **knowledge_plan,
    }


def replan_with_evidence(
    knowledge_context: dict[str, Any],
    *,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    tool_result: Any = None,
    unit_limit: int = 15,
) -> dict[str, Any]:
    updated = copy.deepcopy(knowledge_context or {})
    evidence_ledger = updated.setdefault("evidence_ledger", {})
    evidence_ledger.setdefault("tool_calls", [])
    evidence_ledger.setdefault("consumed_unit_ids", [])
    evidence_ledger.setdefault("citation_refs", [])

    parsed_result = tool_result
    if isinstance(tool_result, str):
        try:
            parsed_result = json.loads(tool_result)
        except Exception:
            parsed_result = tool_result

    tool_success = not (isinstance(parsed_result, dict) and parsed_result.get("error"))
    evidence_ledger["tool_calls"].append(
        {
            "tool_name": tool_name,
            "tool_args": tool_args or {},
            "summary": _summarize_result(parsed_result),
            "success": tool_success,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
    )

    previous_units = ((updated.get("knowledge_plan") or {}).get("active_units") or [])
    for unit in previous_units:
        if tool_name in (unit.get("recommended_skills") or []):
            unit_id = unit.get("unit_id")
            if (
                unit_id
                and unit.get("unit_type") in {"trigger", "evidence_step"}
                and unit_id not in evidence_ledger["consumed_unit_ids"]
            ):
                evidence_ledger["consumed_unit_ids"].append(unit_id)
            citation = unit.get("citation")
            if citation and citation not in evidence_ledger["citation_refs"]:
                evidence_ledger["citation_refs"].append(citation)

    if isinstance(parsed_result, dict) and parsed_result.get("error") == "no_host_configured":
        updated["host_configured"] = False

    routed_docs = updated.get("routed_documents") or []
    knowledge_plan = route_playbooks(
        routed_docs,
        unit_limit=unit_limit,
        user_message=updated.get("user_message") or "",
        issue_categories=updated.get("issue_categories") or ["general"],
        host_configured=bool(updated.get("host_configured")),
        evidence_ledger=evidence_ledger,
    )
    updated["knowledge_plan"] = knowledge_plan
    updated["recommended_documents"] = knowledge_plan.get("active_documents", [])
    updated["knowledge_brief"] = knowledge_plan.get("active_documents", [])[:5]
    updated["last_replan"] = {
        "tool_name": tool_name,
        "tool_success": tool_success,
        "summary": _summarize_result(parsed_result),
        "replanned_at": datetime.now(UTC).isoformat(),
    }
    return updated


def render_knowledge_plan_for_prompt(knowledge_context: dict[str, Any]) -> str:
    if not knowledge_context:
        return ""

    lines = []

    # 渲染主机上下文（如果存在）
    host_context = knowledge_context.get("host_context")
    if host_context:
        lines.append("=== 主机上下文信息 ===")

        # 主机基本信息
        host_info = host_context.get("host_info", {})
        if host_info:
            lines.append(f"主机名称: {host_info.get('name')}")
            lines.append(f"主机地址: {host_info.get('host')}:{host_info.get('port')}")
            if host_info.get('os_version'):
                lines.append(f"操作系统: {host_info.get('os_version')}")

        # 最新指标
        latest_metrics = host_context.get("latest_metrics")
        if latest_metrics:
            lines.append(f"当前资源使用率:")
            if latest_metrics.get("cpu_usage") is not None:
                lines.append(f"  - CPU: {latest_metrics.get('cpu_usage'):.1f}%")
            if latest_metrics.get("memory_usage") is not None:
                lines.append(f"  - 内存: {latest_metrics.get('memory_usage'):.1f}%")
            if latest_metrics.get("disk_usage") is not None:
                lines.append(f"  - 磁盘: {latest_metrics.get('disk_usage'):.1f}%")

        # TOP 进程
        top_processes = host_context.get("top_processes", [])
        if top_processes:
            lines.append(f"TOP 进程 (共 {len(top_processes)} 个):")
            for proc in top_processes[:5]:
                lines.append(f"  - PID {proc.get('pid')}: {proc.get('command')} (CPU: {proc.get('cpu_percent')}%, MEM: {proc.get('memory_percent')}%)")

        # 网络连接摘要
        network_summary = host_context.get("network_summary", {})
        if network_summary.get("total_connections"):
            lines.append(f"网络连接: 共 {network_summary.get('total_connections')} 个连接")
            top_remotes = network_summary.get("top_remotes", [])
            if top_remotes:
                lines.append("  主要连接目标:")
                for remote in top_remotes[:3]:
                    lines.append(f"    - {remote.get('remote_address')} ({remote.get('count')} 个连接)")

        # 关联数据源
        related_datasource = host_context.get("related_datasource", [])
        if related_datasource:
            lines.append(f"关联数据源 (共 {len(related_datasource)} 个):")
            for ds in related_datasource:
                lines.append(f"  - {ds.get('name')} ({ds.get('db_type')}) - 状态: {ds.get('connection_status')}")

        lines.append("")

    knowledge_plan = knowledge_context.get("knowledge_plan") or {}
    active_documents = knowledge_plan.get("active_documents") or []
    active_units = knowledge_plan.get("active_units") or []
    lines.extend([
        "Knowledge orchestration plan (must be followed before fallback browsing):",
        "- Use the active knowledge units as the primary diagnostic guidance.",
        "- Prefer the recommended skills from the knowledge plan; only deviate when new evidence justifies it.",
        "- Do not cite a knowledge source unless it appears in the active units or evidence ledger.",
    ])
    if active_documents:
        lines.append("- Active documents:")
        for index, item in enumerate(active_documents[:5], start=1):
            lines.append(
                f"  {index}. [{item.get('scope')}/{item.get('doc_kind')}/{item.get('quality_status')}] "
                f"{item.get('title')} | reason={item.get('reason') or '匹配当前上下文'} | document_id={item.get('document_id')}"
            )
    if active_units:
        lines.append("- Active knowledge units:")
        for index, item in enumerate(active_units[:8], start=1):
            lines.append(
                f"  {index}. ({item.get('unit_type')}) {item.get('citation')} | "
                f"recommended_skills={', '.join(item.get('recommended_skills') or []) or 'none'} | "
                f"summary={item.get('summary') or '无摘要'}"
            )
    recommended_skills = knowledge_plan.get("recommended_skills") or []
    if recommended_skills:
        lines.append(f"- Recommended next skills: {', '.join(recommended_skills[:8])}")
    stop_conditions = knowledge_plan.get("stop_conditions") or []
    if stop_conditions:
        lines.append("- Stop conditions:")
        for item in stop_conditions[:6]:
            lines.append(f"  - {item}")
    evidence_ledger = knowledge_context.get("evidence_ledger") or {}
    if evidence_ledger.get("tool_calls"):
        lines.append("- Evidence ledger:")
        for item in evidence_ledger["tool_calls"][-5:]:
            lines.append(
                f"  - {item.get('tool_name')}: {item.get('summary')} "
                f"(success={str(bool(item.get('success'))).lower()})"
            )
    lines.append("- Final response must include a `### 知识依据` section citing active knowledge units as `文档标题 / 节点标题`.")
    return "\n".join(lines)


async def build_knowledge_context(
    db: AsyncSession,
    *,
    datasource_id: Optional[int],
    host_id: Optional[int] = None,
    user_message: str,
    issue_category: Optional[str] = None,
    diagnostic_brief: Optional[dict[str, Any]] = None,
    document_limit: int = 5,
    unit_limit: int = 15,
) -> dict[str, Any]:
    datasource = None
    db_type = None
    host_configured = False

    if datasource_id:
        result = await db.execute(
            select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
        )
        datasource = result.scalar_one_or_none()
        if datasource:
            if host_id is None:
                host_id = datasource.host_id
            db_type = datasource.db_type
            host_configured = host_id is not None
    elif host_id is not None:
        host_configured = True

    if issue_category is None:
        intent = analyze_query_intent(user_message or "")
        issue_category = intent.issue_category
    issue_categories = infer_issue_categories_from_text(user_message, issue_category)

    if diagnostic_brief is None and datasource_id:
        diagnostic_brief = await build_diagnostic_brief(
            db,
            datasource_id=datasource_id,
            user_message=user_message,
            issue_category=issue_category,
        )

    compatibility_db_types = _compatibility_db_types(db_type)
    query = (
        select(DocDocument, DocCategory.name.label("category_name"), DocCategory.db_type.label("category_db_type"))
        .join(DocCategory, DocDocument.category_id == DocCategory.id)
        .where(
            DocDocument.is_active == True,
            alive_filter(DocDocument),
            DocDocument.enabled_in_diagnosis == True,
        )
    )
    if db_type:
        query = query.where(DocCategory.db_type.in_(compatibility_db_types))

    result = await db.execute(query)
    ranked: list[dict[str, Any]] = []
    dirty = False
    for row in result.all():
        doc = row.DocDocument
        if not doc.compiled_snapshot or not doc.compiled_at:
            await ensure_document_compiled(db, doc, commit=False)
            dirty = True

        route = compute_document_route(
            doc={
                "id": doc.id,
                "title": doc.title,
                "summary": doc.summary,
                "scope": doc.scope,
                "doc_kind": doc.doc_kind,
                "db_types": doc.db_types,
                "issue_categories": doc.issue_categories,
                "datasource_ids": doc.datasource_ids,
                "host_ids": doc.host_ids,
                "tags": doc.tags,
                "priority": doc.priority,
                "freshness_level": doc.freshness_level,
                "category_name": row.category_name,
                "category_db_type": row.category_db_type,
                "diagnosis_profile": doc.diagnosis_profile,
                "quality_status": doc.quality_status,
            },
            user_message=user_message,
            datasource_id=datasource_id,
            host_id=host_id,
            db_type=db_type,
            issue_categories=issue_categories,
            diagnostic_brief=diagnostic_brief,
        )
        if route["score"] < 0:
            continue
        ranked.append(
            {
                "document_id": doc.id,
                "title": doc.title,
                "summary": doc.summary or "",
                "category_name": row.category_name,
                "db_type": row.category_db_type,
                "scope": doc.scope or "builtin",
                "doc_kind": doc.doc_kind or "reference",
                "score": route["score"],
                "reason": "；".join(route["reasons"][:3]) if route["reasons"] else "匹配当前诊断上下文",
                "reasons": route["reasons"],
                "quality_status": doc.quality_status or "draft",
                "diagnosis_profile": normalize_diagnosis_profile(doc.diagnosis_profile),
                "compiled_snapshot": doc.compiled_snapshot or {},
                "compiled_snapshot_summary": doc.compiled_snapshot_summary,
            }
        )

    if dirty:
        await db.commit()

    ranked.sort(key=lambda item: (-item["score"], item["title"]))
    routed_docs = ranked[:document_limit]
    evidence_ledger = {
        "tool_calls": [],
        "consumed_unit_ids": [],
        "citation_refs": [],
    }
    knowledge_plan = route_playbooks(
        routed_docs,
        unit_limit=unit_limit,
        user_message=user_message,
        issue_categories=issue_categories,
        host_configured=host_configured,
        evidence_ledger=evidence_ledger,
    )
    recommended = knowledge_plan.get("active_documents", [])
    return {
        "datasource_id": datasource_id,
        "datasource_name": datasource.name if datasource else None,
        "db_type": db_type,
        "compatibility_db_types": compatibility_db_types,
        "host_id": host_id,
        "host_configured": host_configured,
        "issue_category": issue_category,
        "issue_categories": issue_categories,
        "diagnostic_brief": diagnostic_brief,
        "user_message": user_message,
        "routed_documents": routed_docs,
        "knowledge_plan": knowledge_plan,
        "evidence_ledger": evidence_ledger,
        "recommended_documents": recommended,
        "knowledge_brief": recommended[:5],
    }
