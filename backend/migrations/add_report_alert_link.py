"""
Migration: add alert_id column to reports table.
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
            "WHERE table_name = 'reports' AND column_name = 'alert_id'"
        ))
        if result.scalar_one_or_none():
            logger.info("Column alert_id already exists in reports")
            return

        await conn.execute(text(
            "ALTER TABLE reports ADD COLUMN alert_id INTEGER NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reports_alert_id ON reports (alert_id)"
        ))
        logger.info("Migration complete: added alert_id to reports")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
