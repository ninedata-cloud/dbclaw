"""End-to-end test for skill authorization flow"""
import sys
sys.path.insert(0, '/Users/william/prog/dbclaw')

from backend.agent.skill_authorization import (
    normalize_skill_authorizations,
    filter_skills_by_authorization,
    GROUP_PLATFORM_OPERATIONS,
    GROUP_HIGH_PRIVILEGE_OPERATIONS,
    GROUP_KNOWLEDGE_RETRIEVAL,
)


class MockSkill:
    def __init__(self, skill_id, category):
        self.id = skill_id
        self.category = category
        self.is_builtin = True


def simulate_frontend_to_backend_flow():
    """Simulate the complete flow from frontend to backend"""

    print("\n=== Simulating Frontend → Backend Flow ===\n")

    # Step 1: Frontend sends skill authorizations
    print("Step 1: Frontend sends authorization config")
    frontend_payload = {
        "platform_operations": True,  # User enabled this
        "high_privilege_operations": False,  # User disabled this
        "knowledge_retrieval": True,  # Default enabled
    }
    print(f"Frontend payload: {frontend_payload}")

    # Step 2: Backend receives and normalizes
    print("\nStep 2: Backend normalizes authorization config")
    normalized = normalize_skill_authorizations(frontend_payload, None)
    print(f"Normalized config: {normalized}")

    # Step 3: Backend filters skills
    print("\nStep 3: Backend filters skills based on authorization")
    all_skills = [
        MockSkill("manage_alert_settings", "平台操作"),
        MockSkill("list_datasource", "平台操作"),
        MockSkill("query_monitoring_history", "平台操作"),
        MockSkill("execute_any_sql", "高权限操作"),
        MockSkill("execute_any_os_command", "高权限操作"),
        MockSkill("fetch_webpage", "知识检索"),
        MockSkill("web_search_bocha", "知识检索"),
        MockSkill("mysql_check_status", "mysql"),
        MockSkill("pg_check_locks", "postgresql"),
    ]
    print(f"Total skills: {len(all_skills)}")

    filtered_skills = filter_skills_by_authorization(all_skills, frontend_payload, None)
    print(f"Filtered skills: {len(filtered_skills)}")
    print(f"Skill IDs: {[s.id for s in filtered_skills]}")

    # Step 4: Verify results
    print("\nStep 4: Verify results")
    expected_skills = {
        "manage_alert_settings",  # platform_operations enabled
        "list_datasource",  # platform_operations enabled
        "query_monitoring_history",  # platform_operations enabled
        "fetch_webpage",  # knowledge_retrieval enabled
        "web_search_bocha",  # knowledge_retrieval enabled
        "mysql_check_status",  # No group, always included
        "pg_check_locks",  # No group, always included
    }

    filtered_ids = {s.id for s in filtered_skills}

    # Should be included
    for skill_id in expected_skills:
        assert skill_id in filtered_ids, f"Expected skill '{skill_id}' to be included"
        print(f"✓ {skill_id} is included")

    # Should NOT be included
    excluded_skills = {"execute_any_sql", "execute_any_os_command"}
    for skill_id in excluded_skills:
        assert skill_id not in filtered_ids, f"Expected skill '{skill_id}' to be excluded"
        print(f"✓ {skill_id} is excluded")

    print("\n=== All checks passed! ===")


def test_default_behavior():
    """Test that default behavior matches expected security posture"""

    print("\n=== Testing Default Security Posture ===\n")

    # When frontend doesn't send any authorization config (null)
    print("Scenario: Frontend sends null (first load)")
    normalized = normalize_skill_authorizations(None, None)
    print(f"Normalized: {normalized}")

    assert normalized[GROUP_PLATFORM_OPERATIONS] == False, "Platform operations should be disabled by default"
    assert normalized[GROUP_HIGH_PRIVILEGE_OPERATIONS] == False, "High privilege operations should be disabled by default"
    assert normalized[GROUP_KNOWLEDGE_RETRIEVAL] == True, "Knowledge retrieval should be enabled by default"

    print("✓ Default security posture is correct")
    print("  - Platform operations: DISABLED")
    print("  - High privilege operations: DISABLED")
    print("  - Knowledge retrieval: ENABLED")


if __name__ == "__main__":
    test_default_behavior()
    simulate_frontend_to_backend_flow()
    print("\n" + "="*50)
    print("All tests passed successfully!")
    print("="*50 + "\n")
