"""
修复 metric_snapshots 表中的时区问题
将 UTC 时间转换为本地时间（东八区，+8小时）
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import async_session


async def fix_timezone():
    """修复时区问题：将 UTC 时间转换为本地时间（+8小时）"""
    async with async_session() as db:
        try:
            result = await db.execute(
                text("SELECT COUNT(*) FROM metric_snapshots")
            )
            total_count = result.scalar()
            print(f"总共有 {total_count} 条记录")

            if total_count == 0:
                print("没有数据需要修复")
                return

            print("开始修复时区...")
            await db.execute(
                text("""
                    UPDATE metric_snapshots
                    SET collected_at = collected_at + INTERVAL '8 hours'
                """)
            )
            await db.commit()

            print(f"✓ 成功修复 {total_count} 条记录的时区")

            result = await db.execute(
                text("""
                    SELECT
                        MIN(collected_at) as earliest,
                        MAX(collected_at) as latest
                    FROM metric_snapshots
                """)
            )
            row = result.fetchone()
            if row:
                print(f"  最早记录: {row[0]}")
                print(f"  最新记录: {row[1]}")

        except Exception as e:
            print(f"✗ 修复失败: {e}")
            await db.rollback()
            raise


if __name__ == '__main__':
    print("=" * 60)
    print("修复 metric_snapshots 时区问题")
    print("=" * 60)
    asyncio.run(fix_timezone())
    print("=" * 60)
    print("修复完成！")
    print("=" * 60)
