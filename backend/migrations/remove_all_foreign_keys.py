"""
移除所有外键约束

执行: python backend/migrations/remove_all_foreign_keys.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import engine


async def remove_all_foreign_keys():
    """移除数据库中所有外键约束"""

    async with engine.begin() as conn:
        print("正在查询所有外键约束...")

        # 查询所有外键约束
        result = await conn.execute(text("""
            SELECT
                tc.table_name,
                tc.constraint_name
            FROM information_schema.table_constraints tc
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            ORDER BY tc.table_name, tc.constraint_name
        """))

        foreign_keys = result.fetchall()

        if not foreign_keys:
            print("未找到任何外键约束")
            return

        print(f"找到 {len(foreign_keys)} 个外键约束\n")

        # 删除每个外键约束
        for table_name, constraint_name in foreign_keys:
            try:
                print(f"删除 {table_name}.{constraint_name}...")
                await conn.execute(text(
                    f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                ))
                print(f"  ✓ 已删除")
            except Exception as e:
                print(f"  ✗ 删除失败: {e}")

        print("\n所有外键约束已移除")
        print("\n注意: 数据库不再强制引用完整性，需要在应用层处理数据一致性")


if __name__ == "__main__":
    asyncio.run(remove_all_foreign_keys())
