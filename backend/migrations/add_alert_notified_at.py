"""
Migration: Add notified_at column to alert_messages table.

This column tracks whether an alert has been successfully notified,
preventing duplicate notifications across dispatcher cycles.
"""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    """Add notified_at column to alert_messages if not exists"""
    async with engine.begin() as conn:
        # Check if column already exists
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'alert_messages' AND column_name = 'notified_at'"
        ))
        if result.scalar_one_or_none():
            logger.info("Column notified_at already exists in alert_messages")
            return

        # Add column
        await conn.execute(text(
            "ALTER TABLE alert_messages ADD COLUMN notified_at TIMESTAMP NULL"
        ))

        # Create index for fast lookup
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_alert_messages_notified_at "
            "ON alert_messages (notified_at)"
        ))

        # Backfill: mark existing alerts that already have delivery logs as notified
        await conn.execute(text(
            "UPDATE alert_messages SET notified_at = updated_at "
            "WHERE id IN ("
            "  SELECT DISTINCT alert_id FROM alert_delivery_log WHERE status = 'sent'"
            ")"
        ))

        logger.info("Migration complete: added notified_at to alert_messages")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
