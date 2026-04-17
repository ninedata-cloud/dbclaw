"""
Migration: add alert_id column to inspection_triggers table.
"""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'inspection_triggers' AND column_name = 'alert_id'"
            ")"
        ))
        if result.scalar_one():
            logger.info("Column alert_id already exists in inspection_triggers")
            return

        await conn.execute(text(
            "ALTER TABLE inspection_triggers ADD COLUMN alert_id INTEGER NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_inspection_triggers_alert_id ON inspection_triggers (alert_id)"
        ))
        logger.info("Migration complete: added alert_id to inspection_triggers")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
