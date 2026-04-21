"""验证数据库字段"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.database import engine

async def check_fields():
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'host'
            AND column_name IN ('config_data', 'config_collected_at')
            ORDER BY column_name
        """))
        rows = result.fetchall()

        if rows:
            print("✓ 字段已成功添加:")
            for row in rows:
                print(f"  - {row[0]}: {row[1]}")
        else:
            print("❌ 字段未找到")

asyncio.run(check_fields())
