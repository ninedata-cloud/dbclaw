from __future__ import annotations

from typing import Any, Iterable


GROUP_PLATFORM_OPERATIONS = "platform_operations"
GROUP_HIGH_PRIVILEGE_OPERATIONS = "high_privilege_operations"
GROUP_KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"


SKILL_AUTHORIZATION_GROUPS: list[dict[str, Any]] = [
    {
        "id": GROUP_PLATFORM_OPERATIONS,
        "label": "平台操作",
        "description": "允许 AI 调用平台操作类 skill，例如数据源管理、主机管理、技能管理、告警配置等。",
        "warning_level": "medium",
        "categories": {"平台操作", "system"},
    },
    {
        "id": GROUP_HIGH_PRIVILEGE_OPERATIONS,
        "label": "高权限操作",
        "description": "允许 AI 调用高危变更类 skill，例如任意 SQL、任意 OS 命令等。",
        "warning_level": "high",
        "categories": {"高权限操作", "admin"},
    },
    {
        "id": GROUP_KNOWLEDGE_RETRIEVAL,
        "label": "知识检索",
        "description": "允许 AI 调用知识检索类 skill，以及内置诊断文档检索工具。",
        "warning_level": "low",
        "categories": {"知识检索"},
    },
]

SKILL_AUTHORIZATION_GROUP_BY_ID = {
    item["id"]: item for item in SKILL_AUTHORIZATION_GROUPS
}

SKILL_AUTHORIZATION_GROUP_BY_CATEGORY = {
    category: item["id"]
    for item in SKILL_AUTHORIZATION_GROUPS
    for category in item["categories"]
}

DEFAULT_SKILL_AUTHORIZATIONS: dict[str, bool] = {
    item["id"]: (item["id"] == GROUP_KNOWLEDGE_RETRIEVAL)
    for item in SKILL_AUTHORIZATION_GROUPS
}

STATIC_GROUP_ITEMS: dict[str, list[dict[str, str]]] = {
    GROUP_KNOWLEDGE_RETRIEVAL: [
        {
            "id": "list_documents",
            "name": "知识目录浏览",
            "description": "浏览内置诊断文档目录。",
            "kind": "tool",
        },
        {
            "id": "read_document",
            "name": "知识文档读取",
            "description": "读取内置诊断文档的详细内容。",
            "kind": "tool",
        },
    ]
}

STATIC_TOOL_GROUP_MAP = {
    item["id"]: group_id
    for group_id, items in STATIC_GROUP_ITEMS.items()
    for item in items
}

LEGACY_DISABLED_TOOL_GROUP_MAP = {
    "manage_alert_settings": GROUP_PLATFORM_OPERATIONS,
    "list_datasource": GROUP_PLATFORM_OPERATIONS,
    "manage_datasource": GROUP_PLATFORM_OPERATIONS,
    "manage_host": GROUP_PLATFORM_OPERATIONS,
    "manage_skill": GROUP_PLATFORM_OPERATIONS,
    "query_system_metadata": GROUP_PLATFORM_OPERATIONS,
    "query_monitoring_history": GROUP_PLATFORM_OPERATIONS,
    "query_alert_statistics": GROUP_PLATFORM_OPERATIONS,
    "execute_any_sql": GROUP_HIGH_PRIVILEGE_OPERATIONS,
    "execute_any_os_command": GROUP_HIGH_PRIVILEGE_OPERATIONS,
    "fetch_webpage": GROUP_KNOWLEDGE_RETRIEVAL,
    "web_search_bocha": GROUP_KNOWLEDGE_RETRIEVAL,
    "list_documents": GROUP_KNOWLEDGE_RETRIEVAL,
    "read_document": GROUP_KNOWLEDGE_RETRIEVAL,
}


def get_default_skill_authorizations() -> dict[str, bool]:
    return dict(DEFAULT_SKILL_AUTHORIZATIONS)


def normalize_skill_authorizations(
    authorizations: dict[str, Any] | None = None,
    legacy_disabled_tools: Iterable[str] | None = None,
) -> dict[str, bool]:
    normalized = get_default_skill_authorizations()

    if isinstance(authorizations, dict):
        for group_id in SKILL_AUTHORIZATION_GROUP_BY_ID:
            if group_id not in authorizations:
                continue
            normalized[group_id] = bool(authorizations.get(group_id))

    for tool_name in legacy_disabled_tools or []:
        group_id = LEGACY_DISABLED_TOOL_GROUP_MAP.get(str(tool_name).strip())
        if group_id:
            normalized[group_id] = False

    return normalized


def get_group_id_for_skill(skill: Any) -> str | None:
    category = str(getattr(skill, "category", "") or "").strip()
    return SKILL_AUTHORIZATION_GROUP_BY_CATEGORY.get(category)


def is_skill_authorized(
    skill: Any,
    authorizations: dict[str, Any] | None = None,
    legacy_disabled_tools: Iterable[str] | None = None,
) -> bool:
    group_id = get_group_id_for_skill(skill)
    if not group_id:
        return True
    normalized = normalize_skill_authorizations(authorizations, legacy_disabled_tools)
    return bool(normalized.get(group_id, True))


def filter_skills_by_authorization(
    skills: Iterable[Any],
    authorizations: dict[str, Any] | None = None,
    legacy_disabled_tools: Iterable[str] | None = None,
) -> list[Any]:
    normalized = normalize_skill_authorizations(authorizations, legacy_disabled_tools)
    result = []
    for skill in skills:
        group_id = get_group_id_for_skill(skill)
        if not group_id:
            result.append(skill)
            continue
        if normalized.get(group_id, True):
            result.append(skill)
    return result


def is_static_tool_authorized(
    tool_name: str,
    authorizations: dict[str, Any] | None = None,
    legacy_disabled_tools: Iterable[str] | None = None,
) -> bool:
    group_id = STATIC_TOOL_GROUP_MAP.get(str(tool_name or "").strip())
    if not group_id:
        return True
    normalized = normalize_skill_authorizations(authorizations, legacy_disabled_tools)
    return bool(normalized.get(group_id, True))


def build_skill_authorization_catalog(skills: Iterable[Any]) -> list[dict[str, Any]]:
    grouped_items: dict[str, list[dict[str, Any]]] = {
        item["id"]: [] for item in SKILL_AUTHORIZATION_GROUPS
    }

    for skill in skills:
        group_id = get_group_id_for_skill(skill)
        if not group_id:
            continue
        grouped_items[group_id].append(
            {
                "id": getattr(skill, "id", ""),
                "name": getattr(skill, "name", "") or getattr(skill, "id", ""),
                "description": getattr(skill, "description", "") or "",
                "kind": "skill",
                "category": getattr(skill, "category", None),
            }
        )

    catalog: list[dict[str, Any]] = []
    defaults = get_default_skill_authorizations()
    for group in SKILL_AUTHORIZATION_GROUPS:
        group_id = group["id"]
        items = list(grouped_items[group_id])
        items.extend(STATIC_GROUP_ITEMS.get(group_id, []))
        items.sort(key=lambda item: (item.get("kind") != "skill", item.get("name") or item.get("id") or ""))
        catalog.append(
            {
                "id": group_id,
                "label": group["label"],
                "description": group["description"],
                "warning_level": group["warning_level"],
                "enabled_by_default": defaults[group_id],
                "items": items,
                "item_count": len(items),
            }
        )

    return catalog
