"""
Add composite index for datasource_metric query optimization
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
            # Check if index already exists using pg_indexes
            result = await db.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname = current_schema()
                AND tablename = 'datasource_metric'
                AND indexname = 'idx_datasource_metric_composite'
            """))
            if result.scalar_one_or_none():
                logger.info("Composite index already exists, skipping")
                return

            # Create composite index (DESC for latest data queries)
            await db.execute(text("""
                CREATE INDEX idx_datasource_metric_composite
                ON datasource_metric(datasource_id, metric_type, collected_at DESC)
            """))

            # Create composite index (ASC for historical data queries)
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_datasource_metric_composite_asc
                ON datasource_metric(datasource_id, metric_type, collected_at ASC)
            """))
            await db.commit()
            logger.info("Successfully created composite indexes on datasource_metric")
        except Exception as e:
            logger.error(f"Failed to create composite index: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(add_composite_index())
