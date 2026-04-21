"""Add performance indexes to report table"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    """Add indexes to report table for better query performance"""
    async with async_session() as db:
        try:
            # Check existing indexes via pg_indexes
            result = await db.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname = current_schema()
                AND tablename = 'report'
            """))
            existing_indexes = {row[0] for row in result.fetchall()}

            indexes_to_create = [
                ("idx_report_datasource_id", "CREATE INDEX IF NOT EXISTS idx_report_datasource_id ON report(datasource_id)"),
                ("idx_report_datasource_created_at", "CREATE INDEX IF NOT EXISTS idx_report_datasource_created_at ON report(datasource_id, created_at DESC)"),
                ("idx_report_status", "CREATE INDEX IF NOT EXISTS idx_report_status ON report(status)"),
                ("idx_report_trigger_type", "CREATE INDEX IF NOT EXISTS idx_report_trigger_type ON report(trigger_type)"),
                ("idx_report_created_at", "CREATE INDEX IF NOT EXISTS idx_report_created_at ON report(created_at DESC)"),
                ("idx_report_composite", "CREATE INDEX IF NOT EXISTS idx_report_composite ON report(datasource_id, status, trigger_type, created_at DESC)"),
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
