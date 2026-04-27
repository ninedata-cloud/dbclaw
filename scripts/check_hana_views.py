#!/usr/bin/env python3
"""
Check HANA system view structures
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.skills.context import SkillContext
from backend.database import get_db

DATASOURCE_ID = 379

async def check_view(context, view_name):
    """Check columns in a system view"""
    print(f"\n{'='*60}")
    print(f"Checking {view_name}")
    print(f"{'='*60}")

    query = f"SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS WHERE SCHEMA_NAME='SYS' AND TABLE_NAME='{view_name}' ORDER BY POSITION"

    result = await context.execute_query(query, DATASOURCE_ID)

    if result.get('success'):
        columns = [row[0] for row in result.get('data', [])]
        print(f"Columns ({len(columns)}): {', '.join(columns)}")
    else:
        print(f"Error: {result.get('error')}")

async def main():
    """Check all relevant system views"""

    async for db in get_db():
        context = SkillContext(db=db, user_id=1, permissions=['execute_query'])

        views = [
            'M_EXPENSIVE_STATEMENTS',
            'M_TABLES',
            'M_TABLE_PERSISTENCE_STATISTICS',
            'M_BLOCKED_TRANSACTIONS',
            'M_CS_TABLES',
        ]

        for view in views:
            await check_view(context, view)

        # Check for index-related views
        print(f"\n{'='*60}")
        print("Checking index-related views")
        print(f"{'='*60}")
        query = "SELECT TABLE_NAME FROM SYS.TABLES WHERE SCHEMA_NAME='SYS' AND TABLE_NAME LIKE '%INDEX%' ORDER BY TABLE_NAME"
        result = await context.execute_query(query, DATASOURCE_ID)
        if result.get('success'):
            for row in result.get('data', [])[:20]:
                print(row[0])

        break

if __name__ == "__main__":
    asyncio.run(main())
