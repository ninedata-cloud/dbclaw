"""
Add composite index for metric_snapshots query optimization
"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import async_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_composite_index():
    """Add composite index on (datasource_id, metric_type, collected_at) for faster queries"""
    async with async_session() as db:
        try:
            # Check if index already exists
            result = await db.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name='idx_metric_snapshots_composite'
            """))
            if result.scalar_one_or_none():
                logger.info("Composite index already exists, skipping")
                return

            # Create composite index
            await db.execute(text("""
                CREATE INDEX idx_metric_snapshots_composite 
                ON metric_snapshots(datasource_id, metric_type, collected_at DESC)
            """))
            await db.commit()
            logger.info("Successfully created composite index on metric_snapshots")
        except Exception as e:
            logger.error(f"Failed to create composite index: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(add_composite_index())
