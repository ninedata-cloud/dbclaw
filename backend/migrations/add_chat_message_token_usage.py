"""
为 chat_messages 表添加 token 使用量明细字段。
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
            "WHERE table_name = 'chat_messages' "
            "AND column_name IN ('input_tokens', 'output_tokens', 'total_tokens')"
        ))
        existing_columns = {row[0] for row in columns_result.fetchall()}

        if 'input_tokens' not in existing_columns:
            logger.info("Adding input_tokens column to chat_messages table...")
            await conn.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN input_tokens INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE chat_messages SET input_tokens = 0 WHERE input_tokens IS NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE chat_messages ALTER COLUMN input_tokens SET NOT NULL"
            ))

        if 'output_tokens' not in existing_columns:
            logger.info("Adding output_tokens column to chat_messages table...")
            await conn.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN output_tokens INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE chat_messages SET output_tokens = 0 WHERE output_tokens IS NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE chat_messages ALTER COLUMN output_tokens SET NOT NULL"
            ))

        if 'total_tokens' not in existing_columns:
            logger.info("Adding total_tokens column to chat_messages table...")
            await conn.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN total_tokens INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE chat_messages SET total_tokens = 0 WHERE total_tokens IS NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE chat_messages ALTER COLUMN total_tokens SET NOT NULL"
            ))

        if existing_columns == {'input_tokens', 'output_tokens', 'total_tokens'}:
            logger.info("Token usage columns already exist on chat_messages, skipping migration")
            return

        logger.info("Migration complete: added token usage columns to chat_messages")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
