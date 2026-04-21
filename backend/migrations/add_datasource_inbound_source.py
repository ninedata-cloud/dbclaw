"""
Migration: add inbound_source to datasource.
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


async def _ensure_inbound_source_json(conn) -> None:
    column_type = await _get_inbound_source_type(conn)
    if column_type is None:
        await conn.execute(text(
            "ALTER TABLE datasource ADD COLUMN inbound_source JSON NULL"
        ))
        logger.info("Migration complete: added inbound_source to datasource")
        return

    if column_type == "json":
        logger.info("Column inbound_source already exists in datasource as json")
        return

    logger.info("Converting datasource.inbound_source from %s to json", column_type)
    await conn.execute(text(
        """
        ALTER TABLE datasource
        ALTER COLUMN inbound_source TYPE JSON
        USING inbound_source::json
        """
    ))


async def migrate():
    async with engine.begin() as conn:
        await _ensure_inbound_source_json(conn)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
