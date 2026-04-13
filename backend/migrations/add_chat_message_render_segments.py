"""
为 chat_messages 表添加 assistant 渲染分段相关字段。
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
            "AND column_name IN ('run_id', 'render_segments', 'status')"
        ))
        existing_columns = {row[0] for row in columns_result.fetchall()}

        if "run_id" not in existing_columns:
            logger.info("Adding run_id column to chat_messages table...")
            await conn.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN run_id VARCHAR(64)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_run_id ON chat_messages (run_id)"
            ))

        if "render_segments" not in existing_columns:
            logger.info("Adding render_segments column to chat_messages table...")
            await conn.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN render_segments JSON"
            ))

        if "status" not in existing_columns:
            logger.info("Adding status column to chat_messages table...")
            await conn.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN status VARCHAR(32)"
            ))

        if existing_columns == {"run_id", "render_segments", "status"}:
            logger.info("Render segment columns already exist on chat_messages, skipping migration")
            return

        logger.info("Migration complete: added render segment columns to chat_messages")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
