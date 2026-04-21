from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Iterable


COMPILER_VERSION = "knowledge-compiler/v1"
DEFAULT_STOP_CONDITIONS = [
    "关键假设已被工具结果验证或证伪",
    "已覆盖数据库侧核心证据，且必要时覆盖主机侧证据",
    "结论包含明确知识依据且未引用未激活知识单元",
]

_DEFAULT_DIAGNOSIS_PROFILE = {
    "symptom_tags": [],
    "signal_tags": [],
    "recommended_skills": [],
    "applicability_rules": [],
    "evidence_requirements": [],
    "related_doc_ids": [],
}

_GENERIC_DB_SKILL_ALIASES = {
    "get_db_status": "{prefix}_get_db_status",
    "get_db_variables": "{prefix}_get_db_variables",
    "get_process_list": "{prefix}_get_process_list",
    "get_slow_queries": "{prefix}_get_slow_queries",
    "get_table_stats": "{prefix}_get_table_stats",
    "get_replication_status": "{prefix}_get_replication_status",
    "get_db_size": "{prefix}_get_db_size",
    "explain_query": "{prefix}_explain_query",
    "list_connections": "{prefix}_list_connections",
    "get_index_usage": "{prefix}_get_index_usage",
    "get_wait_events": "{prefix}_get_wait_events",
    "get_wait_stats": "{prefix}_get_wait_stats",
    "get_vacuum_stats": "{prefix}_get_vacuum_stats",
    "get_tablespace_usage": "{prefix}_get_tablespace_usage",
}

_DB_PREFIX_BY_TYPE = {
    "mysql": "mysql",
    "tdsql-c-mysql": "mysql",
    "postgresql": "pg",
    "oracle": "oracle",
    "sqlserver": "mssql",
    "opengauss": "opengauss",
}

_KNOWN_SKILL_PATTERN = re.compile(r"\b([a-z][a-z0-9_]{2,})\b")
_BACKTICK_SKILL_PATTERN = re.compile(r"`([a-z][a-z0-9_]{2,})`")
_SECTION_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_DBCLAW_COMMENT_PATTERN = re.compile(r"<!--\s*dbclaw(?::|\s+)(.*?)-->", re.IGNORECASE | re.DOTALL)
_DBCLAW_FENCE_PATTERN = re.compile(r"```dbclaw\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_SQL_BLOCK_PATTERN = re.compile(r"```(?:sql|bash|shell|python)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _normalize_json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    return {}


def normalize_diagnosis_profile(profile: Any) -> dict[str, Any]:
    raw = _normalize_json_object(profile)
    normalized = dict(_DEFAULT_DIAGNOSIS_PROFILE)
    normalized["symptom_tags"] = _dedupe_strings(raw.get("symptom_tags") or [])
    normalized["signal_tags"] = _dedupe_strings(raw.get("signal_tags") or [])
    normalized["recommended_skills"] = _dedupe_strings(raw.get("recommended_skills") or [])
    normalized["applicability_rules"] = [
        item for item in (raw.get("applicability_rules") or []) if isinstance(item, dict)
    ]
    normalized["evidence_requirements"] = [
        item for item in (raw.get("evidence_requirements") or []) if isinstance(item, dict)
    ]
    normalized["related_doc_ids"] = [
        int(item) for item in (raw.get("related_doc_ids") or []) if str(item).isdigit()
    ]
    for key, value in raw.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def _parse_dbclaw_blocks(content: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for pattern in (_DBCLAW_COMMENT_PATTERN, _DBCLAW_FENCE_PATTERN):
        for match in pattern.finditer(content or ""):
            raw = (match.group(1) or "").strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw, "parse_error": True}
            if isinstance(parsed, dict):
                blocks.append(parsed)
    return blocks


def _strip_markdown(text: str) -> str:
    if not text:
        return ""
    stripped = re.sub(r"```[\s\S]*?```", " ", text)
    stripped = re.sub(r"`([^`]*)`", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"^#{1,6}\s*", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^[-*+>|\s]+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def _split_markdown_sections(content: str) -> list[dict[str, Any]]:
    lines = (content or "").splitlines()
    sections: list[dict[str, Any]] = []
    current_title = "文档概览"
    current_heading = "文档概览"
    current_level = 1
    current_lines: list[str] = []
    title_stack: list[str] = []

    def flush_current() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append(
                {
                    "heading": current_heading,
                    "title": current_title,
                    "level": current_level,
                    "body": body,
                }
            )

    for line in lines:
        match = _SECTION_HEADING_PATTERN.match(line.strip())
        if match:
            flush_current()
            current_lines = []
            current_level = len(match.group(1))
            current_heading = match.group(2).strip()
            title_stack = title_stack[: current_level - 1]
            title_stack.append(current_heading)
            current_title = " / ".join(title_stack)
            continue
        current_lines.append(line)

    flush_current()
    return sections


def _classify_unit_type(title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    heading = title.lower()
    if any(keyword in heading for keyword in ["风险", "注意", "限制", "禁用"]):
        return "risk"
    if any(keyword in heading for keyword in ["建议", "方案", "优化", "处置", "动作", "应急"]):
        return "action"
    if any(keyword in heading for keyword in ["阈值", "判断", "评估", "结论", "标准", "正常范围"]):
        return "decision_rule"
    if any(keyword in heading for keyword in ["触发", "适用", "症状", "场景", "前提", "概述"]):
        return "trigger"
    if any(keyword in heading for keyword in ["步骤", "检查", "核查", "分析", "调用", "排查", "获取", "第一步", "第二步", "第三步", "第四步", "第五步", "第六步", "第七步", "第八步"]):
        return "evidence_step"
    if any(token in text for token in [">", "<", "正常范围", "告警阈值", "如果", "则", "需立即", "说明"]):
        return "decision_rule"
    if _SQL_BLOCK_PATTERN.search(body):
        return "evidence_step"
    return "citation"


def _extract_candidate_skill_ids(text: str) -> list[str]:
    candidates = []
    candidates.extend(_BACKTICK_SKILL_PATTERN.findall(text or ""))
    for match in _KNOWN_SKILL_PATTERN.findall(text or ""):
        if "_" not in match:
            continue
        if match.startswith(("idx_", "trx_", "pg_", "mysql_", "mssql_", "oracle_", "opengauss_")) or match in _GENERIC_DB_SKILL_ALIASES:
            candidates.append(match)
            continue
        if match in {
            "execute_diagnostic_query",
            "execute_any_sql",
            "execute_os_command",
            "execute_any_os_command",
            "get_os_metrics",
            "get_metric_history",
            "diagnose_high_cpu",
            "diagnose_high_memory",
            "diagnose_disk_space",
            "diagnose_disk_io",
            "diagnose_network",
            "trigger_inspection",
            "list_documents",
            "read_document",
        }:
            candidates.append(match)
    return _dedupe_strings(candidates)


def _resolve_skill_alias(skill_id: str, db_types: list[str], valid_skill_ids: set[str] | None) -> str:
    if not skill_id:
        return skill_id
    if valid_skill_ids is None or skill_id in valid_skill_ids:
        return skill_id
    alias_template = _GENERIC_DB_SKILL_ALIASES.get(skill_id)
    if not alias_template:
        return skill_id
    for db_type in db_types:
        prefix = _DB_PREFIX_BY_TYPE.get(db_type)
        if not prefix:
            continue
        resolved = alias_template.format(prefix=prefix)
        if valid_skill_ids is None or resolved in valid_skill_ids:
            return resolved
    return skill_id


def _extract_recommended_skills(
    title: str,
    body: str,
    *,
    db_types: list[str],
    profile_skills: list[str],
    valid_skill_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    raw_skills = _dedupe_strings(profile_skills + _extract_candidate_skill_ids(f"{title}\n{body}"))
    resolved_skills: list[str] = []
    unknown_skills: list[str] = []
    for skill_id in raw_skills:
        resolved = _resolve_skill_alias(skill_id, db_types, valid_skill_ids)
        if valid_skill_ids and resolved not in valid_skill_ids:
            unknown_skills.append(skill_id)
            continue
        resolved_skills.append(resolved)
    return _dedupe_strings(resolved_skills), _dedupe_strings(unknown_skills)


def _build_unit_id(title: str, unit_type: str, body: str) -> str:
    digest = hashlib.sha1(f"{title}|{unit_type}|{body[:200]}".encode("utf-8")).hexdigest()
    return f"ku_{digest[:12]}"


def compile_document_knowledge(
    *,
    title: str,
    content: str,
    diagnosis_profile: Any = None,
    tags: list[str] | None = None,
    db_types: list[str] | None = None,
    freshness_level: str | None = None,
    valid_skill_ids: set[str] | None = None,
) -> dict[str, Any]:
    normalized_profile = normalize_diagnosis_profile(diagnosis_profile)
    normalized_db_types = _dedupe_strings(db_types or [])
    skill_validation_set = set(valid_skill_ids or []) or None
    sections = _split_markdown_sections(content)
    dbclaw_blocks = _parse_dbclaw_blocks(content)
    warnings: list[str] = []
    units: list[dict[str, Any]] = []
    unit_type_counts: dict[str, int] = {}
    unknown_skills: list[str] = []

    for section in sections:
        unit_type = _classify_unit_type(section["heading"], section["body"])
        recommended_skills, unknown_refs = _extract_recommended_skills(
            section["heading"],
            section["body"],
            db_types=normalized_db_types,
            profile_skills=normalized_profile.get("recommended_skills") or [],
            valid_skill_ids=skill_validation_set,
        )
        summary = _strip_markdown(section["body"])[:220]
        unit = {
            "unit_id": _build_unit_id(section["title"], unit_type, section["body"]),
            "unit_type": unit_type,
            "title": section["heading"],
            "path": section["title"],
            "summary": summary,
            "recommended_skills": recommended_skills,
            "citations": [{"document_title": title, "node_title": section["heading"]}],
            "evidence_requirements": normalized_profile.get("evidence_requirements") or [],
            "signal_tags": normalized_profile.get("signal_tags") or [],
            "symptom_tags": normalized_profile.get("symptom_tags") or [],
            "body_excerpt": section["body"][:1200],
        }
        units.append(unit)
        unit_type_counts[unit_type] = unit_type_counts.get(unit_type, 0) + 1
        unknown_skills.extend(unknown_refs)

    for block in dbclaw_blocks:
        if not isinstance(block, dict):
            continue
        hints = block.get("units")
        if not isinstance(hints, list):
            continue
        for index, hint in enumerate(hints, start=1):
            if not isinstance(hint, dict):
                continue
            unit_type = str(hint.get("unit_type") or "citation").strip() or "citation"
            hint_title = str(hint.get("title") or f"dbclaw_hint_{index}")
            hint_summary = str(hint.get("summary") or hint.get("description") or "").strip()
            recommended_skills, unknown_refs = _extract_recommended_skills(
                hint_title,
                json.dumps(hint, ensure_ascii=False),
                db_types=normalized_db_types,
                profile_skills=hint.get("recommended_skills") or [],
                valid_skill_ids=skill_validation_set,
            )
            units.append(
                {
                    "unit_id": _build_unit_id(hint_title, unit_type, hint_summary or json.dumps(hint, ensure_ascii=False)),
                    "unit_type": unit_type,
                    "title": hint_title,
                    "path": f"dbclaw/{hint_title}",
                    "summary": hint_summary[:220],
                    "recommended_skills": recommended_skills,
                    "citations": [{"document_title": title, "node_title": hint_title}],
                    "evidence_requirements": hint.get("evidence_requirements") or normalized_profile.get("evidence_requirements") or [],
                    "signal_tags": hint.get("signal_tags") or normalized_profile.get("signal_tags") or [],
                    "symptom_tags": hint.get("symptom_tags") or normalized_profile.get("symptom_tags") or [],
                    "body_excerpt": hint_summary[:1200],
                    "source": "dbclaw",
                }
            )
            unit_type_counts[unit_type] = unit_type_counts.get(unit_type, 0) + 1
            unknown_skills.extend(unknown_refs)

    if not units:
        warnings.append("未提取到可路由的知识单元")
    if unit_type_counts.get("trigger", 0) == 0:
        warnings.append("缺少触发条件")
    if unit_type_counts.get("action", 0) == 0:
        warnings.append("缺少动作建议")
    if not any(unit.get("recommended_skills") for unit in units):
        warnings.append("未识别到可验证的技能引用")
    if unknown_skills:
        warnings.append(f"未识别技能引用: {', '.join(_dedupe_strings(unknown_skills)[:8])}")
    if str(freshness_level or "").lower() == "expired":
        warnings.append("文档已过期")

    quality_status = "expired" if str(freshness_level or "").lower() == "expired" else ("warning" if warnings else "ready")
    version_hash = hashlib.sha1(
        json.dumps(
            {
                "title": title,
                "db_types": normalized_db_types,
                "profile": normalized_profile,
                "units": [{k: unit.get(k) for k in ("unit_id", "unit_type", "title", "recommended_skills")} for unit in units],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    compiled_snapshot = {
        "compiler_version": COMPILER_VERSION,
        "compiled_title": title,
        "version_hash": version_hash,
        "db_types": normalized_db_types,
        "tags": _dedupe_strings(tags or []),
        "dbclaw_blocks": dbclaw_blocks,
        "units": units,
        "warnings": _dedupe_strings(warnings),
        "summary": {
            "unit_count": len(units),
            "unit_type_counts": unit_type_counts,
            "skill_count": len(
                {
                    skill_id
                    for unit in units
                    for skill_id in (unit.get("recommended_skills") or [])
                    if skill_id
                }
            ),
            "warning_count": len(_dedupe_strings(warnings)),
        },
    }
    return {
        "diagnosis_profile": normalized_profile,
        "compiled_snapshot": compiled_snapshot,
        "compiled_at": datetime.now(UTC),
        "quality_status": quality_status,
    }


def build_default_stop_conditions(knowledge_units: list[dict[str, Any]], diagnosis_profile: dict[str, Any]) -> list[str]:
    stop_conditions = []
    evidence_requirements = diagnosis_profile.get("evidence_requirements") or []
    for item in evidence_requirements:
        label = str(item.get("label") or item.get("name") or "").strip()
        if label:
            stop_conditions.append(f"已满足证据要求：{label}")
    if any(unit.get("unit_type") == "decision_rule" for unit in knowledge_units):
        stop_conditions.append("已覆盖至少一个决策规则并完成工具验证")
    if any(unit.get("unit_type") == "risk" for unit in knowledge_units):
        stop_conditions.append("已输出风险提示且与证据一致")
    return _dedupe_strings(stop_conditions + DEFAULT_STOP_CONDITIONS)
