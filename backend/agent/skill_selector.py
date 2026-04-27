"""AI Agent skill selector - converts skills to OpenAI function format.

This module also supports filtering skills exposed as tools based on the current
conversation datasource type to reduce LLM tool-schema token usage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from backend.agent.skill_authorization import filter_skills_by_authorization
from backend.models.skill import Skill

logger = logging.getLogger(__name__)


# Skills that are always useful, even when a datasource is selected.
GLOBAL_SKILL_IDS: Set[str] = {
    "execute_diagnostic_query",
    "diagnose_datasource_connection",
    "execute_any_sql",
    "fetch_webpage",
    "web_search_bocha",
    # Platform operations - always available regardless of datasource type
    "list_datasource",
    "query_system_metadata",
    "query_monitoring_history",
    "query_alert_statistics",
    "manage_alert_settings",
    "manage_datasource",
    "manage_host",
    "manage_skill",
    "list_host",
    "query_host_metric",
    # Utility skills - always available
    "get_current_time",
}

# OS diagnostics are only useful when a datasource has an associated host.
OS_SKILL_IDS: Set[str] = {
    "get_os_metrics",
    "execute_os_command",
    "execute_any_os_command",
    "diagnose_high_cpu",
    "diagnose_high_memory",
    "diagnose_disk_space",
    "diagnose_disk_io",
    "diagnose_network",
}

# Mapping from datasource.db_type -> eligible skill families.
# Primary signal: skill id prefix; secondary: category/tags.
DB_TOOL_FAMILY_MAP: dict[str, dict[str, Set[str]]] = {
    "mysql": {
        "prefixes": {"mysql_"},
        "categories": {"mysql"},
        "tags": {"mysql"},
    },
    "tdsql-c-mysql": {
        "prefixes": {"mysql_"},
        "categories": {"mysql"},
        "tags": {"mysql", "tdsql-c-mysql", "tdsql_c_mysql"},
    },
    "postgresql": {
        "prefixes": {"pg_"},
        "categories": {"postgresql"},
        "tags": {"postgresql", "pg"},
    },
    "sqlserver": {
        "prefixes": {"mssql_"},
        "categories": {"sqlserver"},
        "tags": {"sqlserver", "mssql"},
    },
    "oracle": {
        "prefixes": {"oracle_"},
        "categories": {"oracle"},
        "tags": {"oracle"},
    },
    "opengauss": {
        "prefixes": {"opengauss_"},
        "categories": {"opengauss"},
        "tags": {"opengauss"},
    },
    "hana": {
        "prefixes": {"hana_"},
        "categories": {"hana", "sap hana"},
        "tags": {"hana", "sap"},
    },
}


def normalize_db_type(db_type: Optional[str]) -> Optional[str]:
    if not db_type:
        return None
    value = db_type.strip().lower()
    aliases = {
        "postgres": "postgresql",
        "pg": "postgresql",
        "mssql": "sqlserver",
        "sql_server": "sqlserver",
        "tdsql_c_mysql": "tdsql-c-mysql",
    }
    return aliases.get(value, value)


def is_global_skill(skill: Skill) -> bool:
    return (skill.id or "") in GLOBAL_SKILL_IDS


def is_os_skill(skill: Skill) -> bool:
    return (skill.id or "") in OS_SKILL_IDS


def skill_matches_datasource(skill: Skill, db_type: str) -> bool:
    family = DB_TOOL_FAMILY_MAP.get(db_type)
    if not family:
        return False

    skill_id = (skill.id or "").lower()
    if any(skill_id.startswith(prefix) for prefix in family["prefixes"]):
        return True

    category = (skill.category or "").lower()
    if category and category in family["categories"]:
        return True

    tags = {str(t).lower() for t in (skill.tags or [])}
    if tags.intersection(family["tags"]):
        return True

    return False


def skill_to_openai_function(skill: Skill) -> Dict[str, Any]:
    """Convert a Skill to OpenAI function calling format."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in skill.parameters or []:
        param_def: dict[str, Any] = {
            "type": param["type"],
            "description": param["description"],
        }

        if param.get("default") is not None:
            param_def["default"] = param["default"]
        if param.get("enum") is not None:
            param_def["enum"] = param["enum"]
        if param.get("pattern") is not None:
            param_def["pattern"] = param["pattern"]
        if param.get("min") is not None:
            if param["type"] in {"integer", "number"}:
                param_def["minimum"] = param["min"]
            elif param["type"] == "string":
                param_def["minLength"] = int(param["min"])
            elif param["type"] == "array":
                param_def["minItems"] = int(param["min"])
        if param.get("max") is not None:
            if param["type"] in {"integer", "number"}:
                param_def["maximum"] = param["max"]
            elif param["type"] == "string":
                param_def["maxLength"] = int(param["max"])
            elif param["type"] == "array":
                param_def["maxItems"] = int(param["max"])
        if param["type"] == "array":
            param_def["items"] = param.get("items") or {"type": "string"}

        properties[param["name"]] = param_def

        if param.get("required", True):
            required.append(param["name"])

    # Add timeout parameter for dynamic execution time control
    properties["timeout"] = {
        "type": "integer",
        "description": "Execution timeout in seconds (30-3600). Estimate based on task complexity: simple queries 30-60s, complex analysis 300-600s, deep diagnostics 600-3600s.",
        "minimum": 30,
        "maximum": 3600,
    }

    return {
        "type": "function",
        "function": {
            "name": skill.id,
            "description": skill.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


async def get_available_skills_as_tools(
    db,
    skill_authorizations: Optional[Dict[str, Any]] = None,
    disabled_tools: Optional[List[str]] = None,
    datasource_db_type: Optional[str] = None,
    host_configured: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Get enabled skills and convert them to OpenAI tool format.

    - If datasource_db_type is None: return all enabled skills (minus disabled_tools),
      then apply session-level skill authorization filtering.
    - If datasource_db_type is provided: keep only global skills, db-matching skills,
      and OS skills (only when host_configured is True).
    """

    from backend.skills.registry import SkillRegistry

    registry = SkillRegistry(db)
    skills = await registry.list_skills(is_enabled=True, is_builtin=True)
    logger.info(f"[SKILL_AUTH] Before filtering: {len(skills)} skills, skill_authorizations={skill_authorizations}")
    skills = filter_skills_by_authorization(skills, skill_authorizations, disabled_tools)
    logger.info(f"[SKILL_AUTH] After filtering: {len(skills)} skills")

    disabled_set = set(disabled_tools) if disabled_tools else set()

    normalized_db_type = normalize_db_type(datasource_db_type)

    kept: list[Skill] = []

    if not normalized_db_type:
        for skill in skills:
            if not getattr(skill, "is_builtin", False):
                continue
            if skill.id not in disabled_set:
                kept.append(skill)

        logger.info(
            "Skill tools: db_type=None total=%d kept=%d disabled=%d",
            len(skills),
            len(kept),
            len(disabled_set),
        )
        return [skill_to_openai_function(skill) for skill in kept]

    family_exists = normalized_db_type in DB_TOOL_FAMILY_MAP
    if not family_exists:
        logger.warning(
            "No tool family mapping for db_type=%s; keeping only global tools",
            normalized_db_type,
        )

    for skill in skills:
        if not getattr(skill, "is_builtin", False):
            continue
        if skill.id in disabled_set:
            continue

        if is_global_skill(skill):
            kept.append(skill)
            continue

        if is_os_skill(skill):
            if host_configured:
                kept.append(skill)
            continue

        if family_exists and skill_matches_datasource(skill, normalized_db_type):
            kept.append(skill)

    logger.info(
        "Skill tools: db_type=%s total=%d kept=%d disabled=%d host_configured=%s",
        normalized_db_type,
        len(skills),
        len(kept),
        len(disabled_set),
        host_configured,
    )

    return [skill_to_openai_function(skill) for skill in kept]
