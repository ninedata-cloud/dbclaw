"""Add data JSON column to host_metric table"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    """Add data column to host_metric table"""
    async with async_session() as db:
        try:
            # Check if column already exists
            result = await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'host_metric' AND column_name = 'data'"
            ))
            if result.scalar_one_or_none():
                logger.info("host_metric.data column already exists, skipping")
                return

            await db.execute(text(
                "ALTER TABLE host_metric ADD COLUMN data JSON"
            ))
            await db.commit()
            logger.info("Added data column to host_metric table")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            await db.rollback()


if __name__ == "__main__":
    asyncio.run(migrate())
