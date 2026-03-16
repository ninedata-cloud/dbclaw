"""Add resolved_value column to alert_messages table"""
import asyncio
import logging
from backend.database import async_session
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def run_migration():
    async with async_session() as db:
        # Check if column already exists
        result = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'alert_messages' AND column_name = 'resolved_value'
        """))
        if result.fetchone():
            logger.info("resolved_value column already exists")
            return

        await db.execute(text(
            "ALTER TABLE alert_messages ADD COLUMN resolved_value REAL"
        ))
        await db.commit()
        logger.info("Added resolved_value column to alert_messages")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migration())
