"""
Migration: remove datasource-level monitoring interval fields.
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
            "WHERE table_name = 'datasources' AND column_name = 'monitoring_interval'"
        ))
        if result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE datasources DROP COLUMN IF EXISTS monitoring_interval"))
            logger.info("Migration complete: dropped datasources.monitoring_interval")
        else:
            logger.info("Column monitoring_interval already removed from datasources")

        await conn.execute(text("""
            UPDATE datasources
            SET inbound_source = inbound_source - 'schedule'
            WHERE inbound_source IS NOT NULL
              AND inbound_source ? 'schedule'
        """))
        logger.info("Migration complete: removed inbound_source.schedule from datasources")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
