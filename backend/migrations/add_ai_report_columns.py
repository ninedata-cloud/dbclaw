"""
Migration: Add AI-related columns to reports table
"""
import asyncio
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def check_column_exists(db, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    result = await db.execute(text(f"PRAGMA table_info({table_name})"))
    columns = result.fetchall()
    return any(col[1] == column_name for col in columns)


async def migrate():
    """Add AI-related columns to reports table"""
    async with async_session() as db:
        try:
            # Check and add ai_analysis column
            if not await check_column_exists(db, "reports", "ai_analysis"):
                await db.execute(text("ALTER TABLE reports ADD COLUMN ai_analysis TEXT"))
                logger.info("Added ai_analysis column to reports table")

            # Check and add ai_model_id column
            if not await check_column_exists(db, "reports", "ai_model_id"):
                await db.execute(text("ALTER TABLE reports ADD COLUMN ai_model_id INTEGER"))
                logger.info("Added ai_model_id column to reports table")

            # Check and add kb_ids column
            if not await check_column_exists(db, "reports", "kb_ids"):
                await db.execute(text("ALTER TABLE reports ADD COLUMN kb_ids JSON"))
                logger.info("Added kb_ids column to reports table")

            # Check and add generation_method column
            if not await check_column_exists(db, "reports", "generation_method"):
                await db.execute(text("ALTER TABLE reports ADD COLUMN generation_method VARCHAR(20) DEFAULT 'rule-based'"))
                logger.info("Added generation_method column to reports table")

            # Check and add error_message column
            if not await check_column_exists(db, "reports", "error_message"):
                await db.execute(text("ALTER TABLE reports ADD COLUMN error_message TEXT"))
                logger.info("Added error_message column to reports table")

            await db.commit()
            logger.info("Migration completed successfully")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
