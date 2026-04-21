"""
为 ai_model 表添加 protocol 字段，并为历史数据回填默认值。
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
            "WHERE table_name = 'ai_model' AND column_name = 'protocol'"
        ))
        if result.fetchone():
            logger.info("protocol column already exists on ai_model, skipping migration")
            return

        logger.info("Adding protocol column to ai_model table...")
        await conn.execute(text(
            "ALTER TABLE ai_model ADD COLUMN protocol VARCHAR(20) DEFAULT 'openai'"
        ))
        await conn.execute(text(
            "UPDATE ai_model SET protocol = 'openai' WHERE protocol IS NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE ai_model ALTER COLUMN protocol SET NOT NULL"
        ))
        logger.info("Migration complete: added protocol column to ai_model")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
