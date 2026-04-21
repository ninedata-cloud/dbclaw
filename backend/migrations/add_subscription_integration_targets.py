"""
Migration: add integration_targets to alert_subscription.
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
            "AND table_name = 'alert_subscription' AND column_name = 'integration_targets'"
            ")"
        ))
        if result.scalar_one():
            logger.info("Column integration_targets already exists in alert_subscription")
            return

        await conn.execute(text(
            "ALTER TABLE alert_subscription ADD COLUMN integration_targets JSON NOT NULL DEFAULT '[]'::json"
        ))
        logger.info("Migration complete: added integration_targets to alert_subscription")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
