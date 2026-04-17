"""
为 ai_models 表添加 context_window 字段。
"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'ai_models' AND column_name = 'context_window'"
        ))
        if result.fetchone():
            logger.info("context_window column already exists on ai_models, skipping migration")
            return

        logger.info("Adding context_window column to ai_models table...")
        await conn.execute(text(
            "ALTER TABLE ai_models ADD COLUMN context_window INTEGER"
        ))
        logger.info("Migration complete: added context_window column to ai_models")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
