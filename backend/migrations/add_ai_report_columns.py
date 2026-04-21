"""
Migration: Add AI-related columns to report table
"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def check_column_exists(db, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    result = await db.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = :table AND column_name = :col
    """), {"table": table_name, "col": column_name})
    return result.fetchone() is not None


async def migrate():
    """Add AI-related columns to report table"""
    async with async_session() as db:
        try:
            # Check and add ai_analysis column
            if not await check_column_exists(db, "report", "ai_analysis"):
                await db.execute(text("ALTER TABLE report ADD COLUMN ai_analysis TEXT"))
                logger.info("Added ai_analysis column to report table")

            # Check and add ai_model_id column
            if not await check_column_exists(db, "report", "ai_model_id"):
                await db.execute(text("ALTER TABLE report ADD COLUMN ai_model_id INTEGER"))
                logger.info("Added ai_model_id column to report table")

            # Check and add kb_ids column
            if not await check_column_exists(db, "report", "kb_ids"):
                await db.execute(text("ALTER TABLE report ADD COLUMN kb_ids JSON"))
                logger.info("Added kb_ids column to report table")

            # Check and add generation_method column
            if not await check_column_exists(db, "report", "generation_method"):
                await db.execute(text("ALTER TABLE report ADD COLUMN generation_method VARCHAR(20) DEFAULT 'rule-based'"))
                logger.info("Added generation_method column to report table")

            # Check and add error_message column
            if not await check_column_exists(db, "report", "error_message"):
                await db.execute(text("ALTER TABLE report ADD COLUMN error_message TEXT"))
                logger.info("Added error_message column to report table")

            await db.commit()
            logger.info("Migration completed successfully")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
