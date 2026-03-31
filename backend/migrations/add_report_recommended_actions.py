"""Migration: add recommended_actions column to reports table."""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'reports' AND column_name = 'recommended_actions'"
        ))
        if result.scalar_one_or_none():
            logger.info("Column recommended_actions already exists in reports")
            return

        await conn.execute(text(
            "ALTER TABLE reports ADD COLUMN recommended_actions JSON NULL"
        ))
        logger.info("Migration complete: added recommended_actions to reports")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
