"""
添加数据源连接状态字段
- connection_status: 连接状态 (normal/warning/failed/unknown)
- connection_error: 连接错误信息
- connection_checked_at: 最后检测时间
"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        # 检查字段是否已存在
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'datasources' AND column_name = 'connection_status'"
        ))
        if result.fetchone():
            logger.info("connection_status column already exists, skipping migration")
            return

        logger.info("Adding connection status columns to datasources table...")

        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN connection_status VARCHAR(20) DEFAULT 'unknown'"
        ))
        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN connection_error TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN connection_checked_at TIMESTAMP"
        ))

        logger.info("Migration complete: added connection status columns")


if __name__ == "__main__":
    asyncio.run(migrate())
