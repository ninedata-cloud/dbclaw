import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        table_exists_result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'chat_event_dedup')"
        ))
        if not bool(table_exists_result.scalar()):
            logger.info("Table chat_event_dedup does not exist, skip migration")
            return

        await conn.execute(text("DROP INDEX IF EXISTS uq_chat_event_dedup_event_id"))
        await conn.execute(text("DROP INDEX IF EXISTS uq_chat_event_dedup_message_id"))

        await conn.execute(text("""
            DELETE FROM chat_event_dedup t
            USING chat_event_dedup newer
            WHERE t.id < newer.id
              AND t.channel_type = newer.channel_type
              AND t.event_type = newer.event_type
              AND t.external_event_id IS NOT NULL
              AND newer.external_event_id IS NOT NULL
              AND t.external_event_id = newer.external_event_id
        """))

        await conn.execute(text("""
            DELETE FROM chat_event_dedup t
            USING chat_event_dedup newer
            WHERE t.id < newer.id
              AND t.channel_type = newer.channel_type
              AND t.event_type = newer.event_type
              AND t.external_message_id IS NOT NULL
              AND newer.external_message_id IS NOT NULL
              AND t.external_message_id = newer.external_message_id
        """))

        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_event_dedup_event_id
            ON chat_event_dedup (channel_type, event_type, external_event_id)
            WHERE external_event_id IS NOT NULL
        """))
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_event_dedup_message_id
            ON chat_event_dedup (channel_type, event_type, external_message_id)
            WHERE external_message_id IS NOT NULL
        """))

        logger.info("Migration complete: deduplicated chat_event_dedup and added unique indexes")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
