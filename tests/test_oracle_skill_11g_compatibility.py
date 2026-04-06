from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.skills.loader import SkillLoader


class FakeContext:
    def __init__(self):
        self.queries = []

    async def execute_query(self, sql, datasource_id):
        self.queries.append((sql, datasource_id))
        return {"success": True, "data": [], "columns": []}


def _load_skill_executor(skill_name: str):
    yaml_path = Path("backend/skills/builtin") / skill_name
    skill_def = SkillLoader.load_from_yaml(yaml_path.read_text())
    namespace = {}
    exec(skill_def.code, namespace)
    return namespace["execute"]


def test_all_oracle_builtin_skills_avoid_fetch_first_for_11g():
    oracle_skills = sorted(Path("backend/skills/builtin").glob("oracle_*.yaml"))
    assert oracle_skills, "expected Oracle builtin skills to exist"

    for skill_file in oracle_skills:
        content = skill_file.read_text()
        assert "FETCH FIRST" not in content, f"{skill_file.name} still uses Oracle 12c+ pagination syntax"


@pytest.mark.asyncio
async def test_oracle_get_slow_queries_uses_rownum_and_sanitizes_limit():
    execute = _load_skill_executor("oracle_get_slow_queries.yaml")
    context = FakeContext()

    await execute(context, {"datasource_id": 7, "limit": "not-a-number"})
    query, datasource_id = context.queries[0]

    assert datasource_id == 7
    assert "ROWNUM <= 20" in query
    assert "FETCH FIRST" not in query


@pytest.mark.asyncio
async def test_oracle_get_wait_events_caps_limit_and_uses_rownum():
    execute = _load_skill_executor("oracle_get_wait_events.yaml")
    context = FakeContext()

    await execute(context, {"datasource_id": 8, "limit": 9999})
    query, datasource_id = context.queries[0]

    assert datasource_id == 8
    assert "ROWNUM <= 200" in query
    assert "FETCH FIRST" not in query


@pytest.mark.asyncio
async def test_oracle_get_table_stats_uses_rownum_wrapper():
    execute = _load_skill_executor("oracle_get_table_stats.yaml")
    context = FakeContext()

    await execute(context, {"datasource_id": 9})
    query, datasource_id = context.queries[0]

    assert datasource_id == 9
    assert "ROWNUM <= 100" in query
    assert "FETCH FIRST" not in query
