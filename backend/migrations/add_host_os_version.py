"""
添加主机 os_version 字段
- os_version: VARCHAR(255), optional, stores operating system version info

运行方式：
python backend/migrations/add_host_os_version.py
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
            "WHERE table_name = 'hosts' AND column_name = 'os_version'"
        ))
        if result.fetchone():
            logger.info("os_version column already exists, skipping migration")
            return

        logger.info("Adding os_version column to hosts table...")

        await conn.execute(text(
            "ALTER TABLE hosts ADD COLUMN os_version VARCHAR(255)"
        ))

        logger.info("Migration complete: added os_version column")


if __name__ == "__main__":
    asyncio.run(migrate())
