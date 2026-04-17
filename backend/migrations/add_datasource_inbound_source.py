"""
Migration: add inbound_source to datasources.
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


async def _ensure_inbound_source_jsonb(conn) -> None:
    column_type = await _get_inbound_source_type(conn)
    if column_type is None:
        await conn.execute(text(
            "ALTER TABLE datasources ADD COLUMN inbound_source JSONB NULL"
        ))
        logger.info("Migration complete: added inbound_source to datasources")
        return

    if column_type == "jsonb":
        logger.info("Column inbound_source already exists in datasources as jsonb")
        return

    logger.info("Converting datasources.inbound_source from %s to jsonb", column_type)
    await conn.execute(text(
        """
        ALTER TABLE datasources
        ALTER COLUMN inbound_source TYPE JSONB
        USING inbound_source::jsonb
        """
    ))


async def migrate():
    async with engine.begin() as conn:
        await _ensure_inbound_source_jsonb(conn)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
