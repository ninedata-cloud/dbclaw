"""
Migration: add inbound_source to datasources.
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
            "WHERE table_name = 'datasources' AND column_name = 'inbound_source'"
        ))
        if result.scalar_one_or_none():
            logger.info("Column inbound_source already exists in datasources")
            return

        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN inbound_source JSONB NULL"
        ))
        logger.info("Migration complete: added inbound_source to datasources")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
