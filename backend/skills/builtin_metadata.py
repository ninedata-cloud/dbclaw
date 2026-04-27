"""
Built-in skill metadata normalization and audit helpers.
"""
from __future__ import annotations

from typing import Iterable, List

from backend.skills.schema import SkillDefinition


BUILTIN_SKILL_CATEGORY_ORDER: list[str] = [
    "通用诊断",
    "MySQL",
    "PostgreSQL",
    "SQL Server",
    "Oracle",
    "openGauss",
    "SAP HANA",
    "平台操作",
    "知识检索",
    "高权限操作",
]

PRIVILEGED_SKILL_IDS = {
    "execute_any_sql",
    "execute_any_os_command",
}

NOTIFICATION_SKILL_IDS = {
    "send_email",
    "send_sms",
    "send_webhook",
}

EXTERNAL_RESEARCH_SKILL_IDS = {
    "fetch_webpage",
    "web_search_bocha",
}

INSPECTION_SKILL_IDS = {
    "trigger_inspection",
}

SYSTEM_MANAGEMENT_SKILL_IDS = {
    "manage_datasource",
    "manage_host",
    "manage_skill",
    "manage_alert_settings",
}

SYSTEM_QUERY_SKILL_IDS = {
    "list_datasource",
    "query_system_metadata",
    "query_monitoring_data",
    "query_monitoring_history",
    "get_metric_history",
    "query_inspection_report",
    "query_alert_statistics",
}

HOST_DIAGNOSTIC_SKILL_IDS = {
    "get_os_metrics",
    "execute_os_command",
    "diagnose_datasource_connection",
    "diagnose_disk_io",
    "diagnose_disk_space",
    "diagnose_high_cpu",
    "diagnose_high_memory",
    "diagnose_network",
}

DATABASE_GENERAL_SKILL_IDS = {
    "execute_diagnostic_query",
}

DATABASE_KEYWORD_FALLBACK = (
    "explain",
    "slow_queries",
    "index_usage",
    "process_list",
    "wait_",
    "vacuum",
    "audit",
    "hot_regions",
    "region_info",
)

DB_CATEGORY_BY_PREFIX: list[tuple[str, str]] = [
    ("mysql_", "MySQL"),
    ("pg_", "PostgreSQL"),
    ("mssql_", "SQL Server"),
    ("oracle_", "Oracle"),
    ("opengauss_", "openGauss"),
    ("hana_", "SAP HANA"),
]

BUILTIN_PERMISSION_OVERRIDES: dict[str, list[str]] = {
    "list_datasource": ["read_datasource"],
    "query_system_metadata": ["read_datasource"],
    "query_monitoring_data": ["read_datasource"],
    "query_monitoring_history": ["read_datasource"],
    "get_metric_history": ["read_datasource"],
    "query_inspection_report": ["read_datasource"],
    "query_alert_statistics": ["read_datasource"],
    "manage_datasource": ["admin"],
    "manage_host": ["admin"],
    "manage_skill": ["admin"],
    "trigger_inspection": ["admin"],
}


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def classify_builtin_skill(skill_id: str) -> str:
    if skill_id in PRIVILEGED_SKILL_IDS:
        return "高权限操作"
    if (skill_id in DATABASE_GENERAL_SKILL_IDS or skill_id in HOST_DIAGNOSTIC_SKILL_IDS):
        return "通用诊断"
    for prefix, category in DB_CATEGORY_BY_PREFIX:
        if skill_id.startswith(prefix):
            return category
    if skill_id in EXTERNAL_RESEARCH_SKILL_IDS:
        return "知识检索"
    if (
        skill_id in NOTIFICATION_SKILL_IDS
        or skill_id in INSPECTION_SKILL_IDS
        or skill_id in SYSTEM_MANAGEMENT_SKILL_IDS
        or skill_id in SYSTEM_QUERY_SKILL_IDS
    ):
        return "平台操作"
    
    if any(keyword in skill_id for keyword in DATABASE_KEYWORD_FALLBACK):
        return "通用诊断"
    return "通用诊断"


def normalize_builtin_permissions(skill_id: str, permissions: list[str]) -> list[str]:
    override = BUILTIN_PERMISSION_OVERRIDES.get(skill_id)
    if not override:
        return permissions
    return dedupe_preserve_order(override + list(permissions or []))


def normalize_builtin_skill_definition(skill_def: SkillDefinition) -> SkillDefinition:
    normalized_category = classify_builtin_skill(skill_def.id)
    normalized_tags = dedupe_preserve_order(skill_def.tags or [])
    normalized_permissions = normalize_builtin_permissions(skill_def.id, skill_def.permissions or [])
    return skill_def.model_copy(
        update={
            "category": normalized_category,
            "tags": normalized_tags,
            "permissions": normalized_permissions,
        }
    )


def sort_skill_categories(categories: Iterable[str]) -> List[str]:
    order_index = {name: idx for idx, name in enumerate(BUILTIN_SKILL_CATEGORY_ORDER)}
    unique = dedupe_preserve_order(categories)
    return sorted(unique, key=lambda item: (order_index.get(item, len(order_index)), item))
