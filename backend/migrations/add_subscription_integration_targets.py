"""
Migration: add integration_targets to alert_subscriptions.
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
            "AND table_name = 'alert_subscriptions' AND column_name = 'integration_targets'"
            ")"
        ))
        if result.scalar_one():
            logger.info("Column integration_targets already exists in alert_subscriptions")
            return

        await conn.execute(text(
            "ALTER TABLE alert_subscriptions ADD COLUMN integration_targets JSONB NOT NULL DEFAULT '[]'::jsonb"
        ))
        logger.info("Migration complete: added integration_targets to alert_subscriptions")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
