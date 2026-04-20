import pytest

from backend.agent.skill_selector import get_available_skills_as_tools


class _FakeSkill:
    def __init__(self, skill_id: str, category: str):
        self.id = skill_id
        self.category = category
        self.description = f"skill {skill_id}"
        self.parameters = []
        self.tags = []
        self.is_builtin = True


@pytest.mark.asyncio
async def test_platform_skills_keep_available_when_authorized(monkeypatch):
    fake_skills = [
        _FakeSkill("manage_datasource", "system"),
        _FakeSkill("manage_host", "system"),
        _FakeSkill("manage_skill", "system"),
        _FakeSkill("mysql_get_db_status", "mysql"),
    ]

    class _FakeRegistry:
        def __init__(self, db):
            self.db = db

        async def list_skills(self, **kwargs):
            return fake_skills

    import backend.skills.registry as registry_module

    monkeypatch.setattr(registry_module, "SkillRegistry", _FakeRegistry)

    tools = await get_available_skills_as_tools(
        db=object(),
        skill_authorizations={
            "platform_operations": True,
            "high_privilege_operations": False,
            "knowledge_retrieval": True,
        },
        datasource_db_type="mysql",
        host_configured=False,
    )

    tool_names = {tool["function"]["name"] for tool in tools}
    assert "manage_datasource" in tool_names
    assert "manage_host" in tool_names
    assert "manage_skill" in tool_names
    assert "mysql_get_db_status" in tool_names
