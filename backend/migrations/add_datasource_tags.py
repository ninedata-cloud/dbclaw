"""
添加数据源 tags 字段
- tags: JSON array of strings

运行方式：
python backend/migrations/add_datasource_tags.py
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
            "WHERE table_name = 'datasources' AND column_name = 'tags'"
        ))
        if result.fetchone():
            logger.info("tags column already exists, skipping migration")
            return

        logger.info("Adding tags column to datasources table...")

        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN tags JSON DEFAULT '[]'::json NOT NULL"
        ))

        logger.info("Migration complete: added tags column")


if __name__ == "__main__":
    asyncio.run(migrate())
