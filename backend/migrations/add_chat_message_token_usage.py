"""
为 chat_message 表添加 token 使用量明细字段。
"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        columns_result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'chat_message' "
            "AND column_name IN ('input_tokens', 'output_tokens', 'total_tokens')"
        ))
        existing_columns = {row[0] for row in columns_result.fetchall()}

        if 'input_tokens' not in existing_columns:
            logger.info("Adding input_tokens column to chat_message table...")
            await conn.execute(text(
                "ALTER TABLE chat_message ADD COLUMN input_tokens INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE chat_message SET input_tokens = 0 WHERE input_tokens IS NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE chat_message ALTER COLUMN input_tokens SET NOT NULL"
            ))

        if 'output_tokens' not in existing_columns:
            logger.info("Adding output_tokens column to chat_message table...")
            await conn.execute(text(
                "ALTER TABLE chat_message ADD COLUMN output_tokens INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE chat_message SET output_tokens = 0 WHERE output_tokens IS NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE chat_message ALTER COLUMN output_tokens SET NOT NULL"
            ))

        if 'total_tokens' not in existing_columns:
            logger.info("Adding total_tokens column to chat_message table...")
            await conn.execute(text(
                "ALTER TABLE chat_message ADD COLUMN total_tokens INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE chat_message SET total_tokens = 0 WHERE total_tokens IS NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE chat_message ALTER COLUMN total_tokens SET NOT NULL"
            ))

        if existing_columns == {'input_tokens', 'output_tokens', 'total_tokens'}:
            logger.info("Token usage columns already exist on chat_message, skipping migration")
            return

        logger.info("Migration complete: added token usage columns to chat_message")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
