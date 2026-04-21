"""
Migration: add alert_id column to report table.
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
            "AND table_name = 'report' AND column_name = 'alert_id'"
            ")"
        ))
        if result.scalar_one():
            logger.info("Column alert_id already exists in report")
            return

        await conn.execute(text(
            "ALTER TABLE report ADD COLUMN alert_id INTEGER NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_report_alert_id ON report (alert_id)"
        ))
        logger.info("Migration complete: added alert_id to report")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
