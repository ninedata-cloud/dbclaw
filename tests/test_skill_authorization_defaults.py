import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agent.skill_authorization import (
    build_skill_authorization_catalog,
    normalize_skill_authorizations,
)


def test_normalize_skill_authorizations_enables_knowledge_retrieval_by_default():
    normalized = normalize_skill_authorizations()

    assert normalized["platform_operations"] is False
    assert normalized["high_privilege_operations"] is False
    assert normalized["knowledge_retrieval"] is True


def test_skill_authorization_catalog_marks_groups_disabled_by_default():
    skills = [
        SimpleNamespace(
            id="query_monitoring_history",
            name="Query Monitoring History",
            description="history",
            category="平台运维",
        ),
        SimpleNamespace(
            id="execute_any_sql",
            name="Execute Any SQL",
            description="dangerous",
            category="高危操作",
        ),
    ]

    catalog = build_skill_authorization_catalog(skills)
    enabled_by_default = {item["id"]: item["enabled_by_default"] for item in catalog}

    assert enabled_by_default["platform_operations"] is False
    assert enabled_by_default["high_privilege_operations"] is False
    assert enabled_by_default["knowledge_retrieval"] is True
