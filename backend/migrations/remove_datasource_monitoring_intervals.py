"""
Migration: remove datasource-level monitoring interval fields.
"""

import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def _get_inbound_source_type(conn) -> str | None:
    result = await conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "AND table_name = 'datasources' AND column_name = 'inbound_source'"
    ))
    return result.scalar_one_or_none()


async def _ensure_inbound_source_jsonb(conn) -> bool:
    column_type = await _get_inbound_source_type(conn)
    if column_type is None:
        logger.info("Column inbound_source does not exist in datasources, skipping schedule cleanup")
        return False

    if column_type == "jsonb":
        return True

    logger.info("Converting datasources.inbound_source from %s to jsonb", column_type)
    await conn.execute(text("""
        ALTER TABLE datasources
        ALTER COLUMN inbound_source TYPE JSONB
        USING inbound_source::jsonb
    """))
    return True


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'datasources' AND column_name = 'monitoring_interval'"
        ))
        if result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE datasources DROP COLUMN IF EXISTS monitoring_interval"))
            logger.info("Migration complete: dropped datasources.monitoring_interval")
        else:
            logger.info("Column monitoring_interval already removed from datasources")

        if await _ensure_inbound_source_jsonb(conn):
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
