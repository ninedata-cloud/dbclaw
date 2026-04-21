"""Test skill authorization filtering fix"""
import sys
sys.path.insert(0, '/Users/william/prog/dbclaw')

from backend.agent.skill_authorization import (
    filter_skills_by_authorization,
    normalize_skill_authorizations,
    GROUP_PLATFORM_OPERATIONS,
    GROUP_HIGH_PRIVILEGE_OPERATIONS,
    GROUP_KNOWLEDGE_RETRIEVAL,
)


class MockSkill:
    def __init__(self, skill_id, category):
        self.id = skill_id
        self.category = category
        self.is_builtin = True


def test_skill_authorization_filtering():
    """Test that skill authorization filtering works correctly"""

    # Create mock skills
    skills = [
        MockSkill("manage_alert_settings", "平台操作"),
        MockSkill("list_datasource", "平台操作"),
        MockSkill("execute_any_sql", "高权限操作"),
        MockSkill("execute_any_os_command", "高权限操作"),
        MockSkill("fetch_webpage", "知识检索"),
        MockSkill("mysql_check_status", "mysql"),  # No group, should always be included
    ]

    # Test 1: Default authorizations (only knowledge_retrieval enabled)
    print("\n=== Test 1: Default authorizations ===")
    default_auth = normalize_skill_authorizations(None, None)
    print(f"Default authorizations: {default_auth}")
    filtered = filter_skills_by_authorization(skills, None, None)
    print(f"Filtered skills: {[s.id for s in filtered]}")
    assert len(filtered) == 2, f"Expected 2 skills (fetch_webpage, mysql_check_status), got {len(filtered)}"
    assert "fetch_webpage" in [s.id for s in filtered]
    assert "mysql_check_status" in [s.id for s in filtered]
    print("✓ Test 1 passed")

    # Test 2: Enable platform_operations
    print("\n=== Test 2: Enable platform_operations ===")
    auth_with_platform = {
        GROUP_PLATFORM_OPERATIONS: True,
        GROUP_HIGH_PRIVILEGE_OPERATIONS: False,
        GROUP_KNOWLEDGE_RETRIEVAL: True,
    }
    normalized = normalize_skill_authorizations(auth_with_platform, None)
    print(f"Normalized authorizations: {normalized}")
    filtered = filter_skills_by_authorization(skills, auth_with_platform, None)
    print(f"Filtered skills: {[s.id for s in filtered]}")
    assert len(filtered) == 4, f"Expected 4 skills, got {len(filtered)}"
    assert "manage_alert_settings" in [s.id for s in filtered]
    assert "list_datasource" in [s.id for s in filtered]
    assert "fetch_webpage" in [s.id for s in filtered]
    assert "mysql_check_status" in [s.id for s in filtered]
    print("✓ Test 2 passed")

    # Test 3: Enable all groups
    print("\n=== Test 3: Enable all groups ===")
    auth_all = {
        GROUP_PLATFORM_OPERATIONS: True,
        GROUP_HIGH_PRIVILEGE_OPERATIONS: True,
        GROUP_KNOWLEDGE_RETRIEVAL: True,
    }
    filtered = filter_skills_by_authorization(skills, auth_all, None)
    print(f"Filtered skills: {[s.id for s in filtered]}")
    assert len(filtered) == 6, f"Expected 6 skills (all), got {len(filtered)}"
    print("✓ Test 3 passed")

    # Test 4: Disable all groups
    print("\n=== Test 4: Disable all groups ===")
    auth_none = {
        GROUP_PLATFORM_OPERATIONS: False,
        GROUP_HIGH_PRIVILEGE_OPERATIONS: False,
        GROUP_KNOWLEDGE_RETRIEVAL: False,
    }
    filtered = filter_skills_by_authorization(skills, auth_none, None)
    print(f"Filtered skills: {[s.id for s in filtered]}")
    assert len(filtered) == 1, f"Expected 1 skill (mysql_check_status), got {len(filtered)}"
    assert "mysql_check_status" in [s.id for s in filtered]
    print("✓ Test 4 passed")

    print("\n=== All tests passed! ===")


if __name__ == "__main__":
    test_skill_authorization_filtering()
