"""
添加数据源 db_version 字段
- db_version: VARCHAR(255), optional, stores database version info

运行方式：
python backend/migrations/add_datasource_db_version.py
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
            "WHERE table_name = 'datasources' AND column_name = 'db_version'"
        ))
        if result.fetchone():
            logger.info("db_version column already exists, skipping migration")
            return

        logger.info("Adding db_version column to datasources table...")

        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN db_version VARCHAR(255)"
        ))

        logger.info("Migration complete: added db_version column")


if __name__ == "__main__":
    asyncio.run(migrate())
