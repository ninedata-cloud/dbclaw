import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        binding_exists_result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'chat_channel_bindings')"
        ))
        binding_exists = bool(binding_exists_result.scalar())
        if not binding_exists:
            await conn.execute(text("""
                CREATE TABLE chat_channel_bindings (
                    id SERIAL PRIMARY KEY,
                    channel_type VARCHAR(50) NOT NULL,
                    external_chat_id VARCHAR(255) NOT NULL,
                    external_user_id VARCHAR(255) NULL,
                    session_id INTEGER NOT NULL,
                    user_id INTEGER NULL,
                    integration_id INTEGER NULL,
                    default_datasource_id INTEGER NULL,
                    default_model_id INTEGER NULL,
                    kb_ids JSON NULL,
                    disabled_tools JSON NULL,
                    last_message_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
            await conn.execute(text("CREATE INDEX ix_chat_channel_bindings_channel_type ON chat_channel_bindings(channel_type)"))
            await conn.execute(text("CREATE INDEX ix_chat_channel_bindings_external_chat_id ON chat_channel_bindings(external_chat_id)"))
            await conn.execute(text("CREATE INDEX ix_chat_channel_bindings_external_user_id ON chat_channel_bindings(external_user_id)"))
            await conn.execute(text("CREATE INDEX ix_chat_channel_bindings_session_id ON chat_channel_bindings(session_id)"))

        dedup_exists_result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'chat_event_dedups')"
        ))
        dedup_exists = bool(dedup_exists_result.scalar())
        if not dedup_exists:
            await conn.execute(text("""
                CREATE TABLE chat_event_dedups (
                    id SERIAL PRIMARY KEY,
                    channel_type VARCHAR(50) NOT NULL,
                    external_event_id VARCHAR(255) NULL,
                    external_message_id VARCHAR(255) NULL,
                    event_type VARCHAR(100) NOT NULL,
                    processed_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
            await conn.execute(text("CREATE INDEX ix_chat_event_dedups_channel_type ON chat_event_dedups(channel_type)"))
            await conn.execute(text("CREATE INDEX ix_chat_event_dedups_external_event_id ON chat_event_dedups(external_event_id)"))
            await conn.execute(text("CREATE INDEX ix_chat_event_dedups_external_message_id ON chat_event_dedups(external_message_id)"))
            await conn.execute(text("CREATE INDEX ix_chat_event_dedups_event_type ON chat_event_dedups(event_type)"))

        logger.info("Migration complete: added feishu chat binding and dedup tables")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
