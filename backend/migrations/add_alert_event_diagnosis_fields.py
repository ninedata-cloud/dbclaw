"""Add root_cause, recommended_actions, diagnosis_status to alert_events table"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def _column_exists(conn, column_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'alert_events'
                  AND column_name = :column_name
            )
            """
        ),
        {"column_name": column_name},
    )
    return bool(result.scalar_one())


async def migrate():
    """Add diagnosis fields to alert_events"""
    async with engine.begin() as conn:
        if not await _column_exists(conn, "root_cause"):
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN root_cause TEXT"))
            logger.info("Added root_cause column to alert_events")
        else:
            logger.info("Column root_cause already exists, skipping")

        if not await _column_exists(conn, "recommended_actions"):
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN recommended_actions TEXT"))
            logger.info("Added recommended_actions column to alert_events")
        else:
            logger.info("Column recommended_actions already exists, skipping")

        if not await _column_exists(conn, "diagnosis_status"):
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN diagnosis_status VARCHAR(20)"))
            logger.info("Added diagnosis_status column to alert_events")
        else:
            logger.info("Column diagnosis_status already exists, skipping")


if __name__ == "__main__":
    asyncio.run(migrate())
