from pathlib import Path

from backend.skills.builtin_metadata import (
    BUILTIN_SKILL_CATEGORY_ORDER,
    classify_builtin_skill,
    normalize_builtin_skill_definition,
)
from backend.skills.loader import SkillLoader
from backend.skills.validator import SkillValidator


BUILTIN_DIR = Path(__file__).parent.parent / "backend/skills/builtin"


def test_all_builtin_skills_load_and_validate():
    yaml_files = sorted(BUILTIN_DIR.glob("*.yaml"))
    assert yaml_files, "No builtin skill YAML files found"

    invalid = []
    for yaml_file in yaml_files:
        skill_def = SkillLoader.load_from_yaml(yaml_file.read_text())
        normalized = normalize_builtin_skill_definition(skill_def)
        is_valid, errors = SkillValidator.validate_code(normalized.code)
        if not is_valid:
            invalid.append((yaml_file.name, errors))

    assert not invalid, f"Builtin skill validation failed: {invalid}"


def test_builtin_skills_are_grouped_into_curated_categories():
    yaml_files = sorted(BUILTIN_DIR.glob("*.yaml"))
    allowed_categories = set(BUILTIN_SKILL_CATEGORY_ORDER)

    unexpected = []
    for yaml_file in yaml_files:
        skill_def = SkillLoader.load_from_yaml(yaml_file.read_text())
        normalized = normalize_builtin_skill_definition(skill_def)
        if normalized.category not in allowed_categories:
            unexpected.append((normalized.id, normalized.category))

    assert not unexpected, f"Unexpected builtin categories: {unexpected}"


def test_database_builtin_skills_keep_db_type_tags_after_regrouping():
    expected_tag_by_prefix = {
        "mysql_": {"mysql"},
        "pg_": {"postgresql"},
        "mssql_": {"sqlserver", "mssql"},
        "oracle_": {"oracle"},
        "dm_": {"dm"},
        "tidb_": {"tidb"},
        "oceanbase_": {"oceanbase"},
        "opengauss_": {"opengauss"},
    }

    missing = []
    for yaml_file in sorted(BUILTIN_DIR.glob("*.yaml")):
        skill_def = SkillLoader.load_from_yaml(yaml_file.read_text())
        normalized = normalize_builtin_skill_definition(skill_def)
        tags = {str(tag).lower() for tag in (normalized.tags or [])}

        for prefix, expected_tags in expected_tag_by_prefix.items():
            if normalized.id.startswith(prefix) and not tags.intersection(expected_tags):
                missing.append((normalized.id, sorted(tags), sorted(expected_tags)))

    assert not missing, f"DB skill tags missing after regrouping: {missing}"


def test_curated_category_examples_match_expected_groups():
    expectations = {
        "execute_diagnostic_query": "数据库通用",
        "mysql_get_db_status": "MySQL",
        "pg_get_slow_queries": "PostgreSQL",
        "mssql_get_db_status": "SQL Server",
        "oracle_get_db_status": "Oracle",
        "tidb_get_db_status": "TiDB",
        "oceanbase_get_db_status": "OceanBase",
        "opengauss_get_db_status": "openGauss",
        "dm_get_db_status": "DM",
        "diagnose_high_cpu": "平台运维",
        "query_monitoring_data": "平台运维",
        "query_monitoring_history": "平台运维",
        "query_alert_statistics": "平台运维",
        "manage_datasource": "平台运维",
        "manage_alert_settings": "平台运维",
        "trigger_inspection": "平台运维",
        "send_webhook": "平台运维",
        "web_search_bocha": "知识检索",
        "execute_any_sql": "高危操作",
    }

    for skill_id, expected_category in expectations.items():
        assert classify_builtin_skill(skill_id) == expected_category
