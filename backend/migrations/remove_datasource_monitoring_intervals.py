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
        "AND table_name = 'datasource' AND column_name = 'inbound_source'"
    ))
    return result.scalar_one_or_none()


async def _ensure_inbound_source_json(conn) -> bool:
    column_type = await _get_inbound_source_type(conn)
    if column_type is None:
        logger.info("Column inbound_source does not exist in datasource, skipping schedule cleanup")
        return False

    if column_type == "json":
        return True

    logger.info("Converting datasource.inbound_source from %s to json", column_type)
    await conn.execute(text("""
        ALTER TABLE datasource
        ALTER COLUMN inbound_source TYPE JSON
        USING inbound_source::json
    """))
    return True


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'datasource' AND column_name = 'monitoring_interval'"
        ))
        if result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE datasource DROP COLUMN IF EXISTS monitoring_interval"))
            logger.info("Migration complete: dropped datasource.monitoring_interval")
        else:
            logger.info("Column monitoring_interval already removed from datasource")

        if await _ensure_inbound_source_json(conn):
            await conn.execute(text("""
                UPDATE datasource
                SET inbound_source = (inbound_source::jsonb - 'schedule')::json
                WHERE inbound_source IS NOT NULL
                  AND inbound_source::jsonb ? 'schedule'
            """))
            logger.info("Migration complete: removed inbound_source.schedule from datasource")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
