#!/usr/bin/env python3
"""
Test HANA skills against real database
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.skills.loader import SkillLoader
from backend.skills.context import SkillContext
from backend.database import get_db

DATASOURCE_ID = 379

async def test_skill(skill_name: str, params: dict):
    """Test a single skill"""
    print(f"\n{'='*60}")
    print(f"Testing: {skill_name}")
    print(f"{'='*60}")

    try:
        yaml_path = Path("backend/skills/builtin") / f"{skill_name}.yaml"
        skill_def = SkillLoader.load_from_yaml(yaml_path.read_text())

        namespace = {}
        exec(skill_def.code, namespace)
        execute = namespace["execute"]

        async for db in get_db():
            context = SkillContext(db=db, user_id=1, permissions=['execute_query', 'admin'])
            result = await execute(context, params)

            print(f"Success: {result.get('success')}")
            if result.get('success'):
                # Print result keys
                print(f"Result keys: {list(result.keys())}")
                # Print first few items of data
                for key, value in result.items():
                    if key == 'success':
                        continue
                    if isinstance(value, list):
                        print(f"{key}: {len(value)} items")
                        if value:
                            print(f"  First item: {value[0]}")
                    elif isinstance(value, dict):
                        print(f"{key}: {value}")
                    else:
                        print(f"{key}: {value}")
            else:
                print(f"Error: {result.get('error')}")
            break

    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Test all HANA skills"""

    skills = [
        ("hana_get_db_status", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_process_list", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_slow_queries", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_variables", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_table_stats", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_replication_status", {"datasource_id": DATASOURCE_ID}),
        ("hana_explain_query", {"datasource_id": DATASOURCE_ID, "sql": "SELECT * FROM DUMMY"}),
        ("hana_get_db_size", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_index_stats", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_table_fragmentation", {"datasource_id": DATASOURCE_ID}),
        ("hana_get_lock_waits", {"datasource_id": DATASOURCE_ID}),
    ]

    for skill_name, params in skills:
        await test_skill(skill_name, params)
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
