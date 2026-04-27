#!/usr/bin/env python3
"""
Check HANA system view structures by querying them directly
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.skills.context import SkillContext
from backend.database import get_db

DATASOURCE_ID = 379

async def check_view_direct(context, view_name, sample_query):
    """Check a view by querying it directly"""
    print(f"\n{'='*60}")
    print(f"Checking {view_name}")
    print(f"{'='*60}")

    result = await context.execute_query(sample_query, DATASOURCE_ID)

    if result.get('success'):
        columns = result.get('columns', [])
        print(f"Columns ({len(columns)}): {', '.join(columns)}")
        data = result.get('data', [])
        print(f"Rows: {len(data)}")
        if data:
            print(f"Sample row: {data[0]}")
    else:
        print(f"Error: {result.get('error')}")

async def main():
    """Check all relevant system views"""

    async for db in get_db():
        context = SkillContext(db=db, user_id=1, permissions=['execute_query'])

        checks = [
            ('M_EXPENSIVE_STATEMENTS', 'SELECT * FROM SYS.M_EXPENSIVE_STATEMENTS LIMIT 1'),
            ('M_TABLES', 'SELECT * FROM SYS.M_TABLES LIMIT 1'),
            ('M_TABLE_PERSISTENCE_STATISTICS', 'SELECT * FROM SYS.M_TABLE_PERSISTENCE_STATISTICS LIMIT 1'),
            ('M_BLOCKED_TRANSACTIONS', 'SELECT * FROM SYS.M_BLOCKED_TRANSACTIONS LIMIT 1'),
            ('M_CS_TABLES', 'SELECT * FROM SYS.M_CS_TABLES LIMIT 1'),
            ('CS_JOIN_INDEXES_', 'SELECT * FROM SYS.CS_JOIN_INDEXES_ LIMIT 1'),
        ]

        for view_name, query in checks:
            await check_view_direct(context, view_name, query)

        break

if __name__ == "__main__":
    asyncio.run(main())
