"""Add performance indexes to reports table"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    """Add indexes to reports table for better query performance"""
    async with async_session() as db:
        try:
            # Check existing indexes via pg_indexes
            result = await db.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'reports'
            """))
            existing_indexes = {row[0] for row in result.fetchall()}

            indexes_to_create = [
                ("idx_reports_datasource_id", "CREATE INDEX IF NOT EXISTS idx_reports_datasource_id ON reports(datasource_id)"),
                ("idx_reports_status", "CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)"),
                ("idx_reports_trigger_type", "CREATE INDEX IF NOT EXISTS idx_reports_trigger_type ON reports(trigger_type)"),
                ("idx_reports_created_at", "CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC)"),
                ("idx_reports_composite", "CREATE INDEX IF NOT EXISTS idx_reports_composite ON reports(datasource_id, status, trigger_type, created_at DESC)"),
            ]

            for idx_name, sql in indexes_to_create:
                if idx_name not in existing_indexes:
                    logger.info(f"Creating index: {idx_name}")
                    await db.execute(text(sql))
                    print(f"Created index: {idx_name}")
                else:
                    print(f"Index already exists: {idx_name}")

            await db.commit()
            print("All indexes created successfully")

        except Exception as e:
            await db.rollback()
            logger.error(f"Migration failed: {e}")
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
