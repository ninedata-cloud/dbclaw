import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.agent.conversation_skills import execute_skill_call
from backend.agent.skill_selector import get_available_skills_as_tools


@pytest.mark.asyncio
async def test_execute_skill_call_rejects_custom_skills():
    custom_skill = SimpleNamespace(
        id="custom_debug",
        name="Custom Debug",
        is_enabled=True,
        is_builtin=False,
    )

    with patch("backend.skills.registry.SkillRegistry.get_skill", new=AsyncMock(return_value=custom_skill)):
        result_json, execution_time_ms, skill_execution_id, visualization = await execute_skill_call(
            "custom_debug",
            {},
            db=object(),
            user_id=1,
        )

    result = json.loads(result_json)
    assert execution_time_ms >= 0
    assert skill_execution_id is None
    assert visualization is None
    assert "Custom skill execution is disabled" in result["error"]


@pytest.mark.asyncio
async def test_get_available_skills_as_tools_only_returns_builtin_skills():
    builtin_skill = SimpleNamespace(
        id="builtin_demo",
        name="Builtin Demo",
        description="builtin",
        parameters=[],
        category="demo",
        tags=[],
        is_builtin=True,
    )
    custom_skill = SimpleNamespace(
        id="custom_demo",
        name="Custom Demo",
        description="custom",
        parameters=[],
        category="demo",
        tags=[],
        is_builtin=False,
    )

    with patch("backend.skills.registry.SkillRegistry.list_skills", new=AsyncMock(return_value=[builtin_skill, custom_skill])):
        tools = await get_available_skills_as_tools(db=object())

    assert [tool["function"]["name"] for tool in tools] == ["builtin_demo"]


@pytest.mark.asyncio
async def test_get_available_skills_as_tools_keeps_query_monitoring_history_when_datasource_scoped():
    history_skill = SimpleNamespace(
        id="query_monitoring_history",
        name="Query Monitoring History",
        description="history",
        parameters=[],
        category="平台运维",
        tags=["monitoring"],
        is_builtin=True,
    )
    mysql_skill = SimpleNamespace(
        id="mysql_get_db_status",
        name="MySQL Status",
        description="mysql",
        parameters=[],
        category="MySQL",
        tags=["mysql"],
        is_builtin=True,
    )

    with patch("backend.skills.registry.SkillRegistry.list_skills", new=AsyncMock(return_value=[history_skill, mysql_skill])):
        tools = await get_available_skills_as_tools(
            db=object(),
            datasource_db_type="mysql",
            host_configured=False,
        )

    assert [tool["function"]["name"] for tool in tools] == [
        "query_monitoring_history",
        "mysql_get_db_status",
    ]
