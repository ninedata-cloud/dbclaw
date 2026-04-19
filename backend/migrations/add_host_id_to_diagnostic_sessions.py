"""
数据库迁移脚本：为 diagnostic_sessions 表添加 host_id 字段
"""
import asyncio
from sqlalchemy import text
from backend.database import async_engine


async def migrate():
    """添加 host_id 字段和索引"""
    async with async_engine.begin() as conn:
        # 添加 host_id 字段
        await conn.execute(text("""
            ALTER TABLE diagnostic_sessions
            ADD COLUMN IF NOT EXISTS host_id INTEGER;
        """))

        # 创建索引
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_diagnostic_sessions_host_id
            ON diagnostic_sessions(host_id);
        """))

        print("✓ 成功添加 host_id 字段到 diagnostic_sessions 表")
        print("✓ 成功创建索引 ix_diagnostic_sessions_host_id")


if __name__ == "__main__":
    asyncio.run(migrate())
