"""
添加主机配置缓存字段

运行方式：
python backend/migrations/add_host_config_cache.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import engine


async def migrate():
    """添加主机配置缓存字段"""
    async with engine.begin() as conn:
        # 添加 config_data 字段
        await conn.execute(text("""
            ALTER TABLE hosts
            ADD COLUMN IF NOT EXISTS config_data JSONB
        """))

        # 添加 config_collected_at 字段
        await conn.execute(text("""
            ALTER TABLE hosts
            ADD COLUMN IF NOT EXISTS config_collected_at TIMESTAMP
        """))

        print("✓ 已添加 hosts.config_data 和 hosts.config_collected_at 字段")


if __name__ == "__main__":
    asyncio.run(migrate())
    print("迁移完成")
