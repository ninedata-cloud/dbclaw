"""
Migration: create integration_bot_binding table.
"""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS integration_bot_binding (
                id SERIAL PRIMARY KEY,
                integration_id INTEGER NOT NULL,
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(200) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                params JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_integration_bot_binding_integration_id ON integration_bot_binding (integration_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_integration_bot_binding_enabled ON integration_bot_binding (enabled)"
        ))
        logger.info("Migration complete: ensured integration_bot_binding exists")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
