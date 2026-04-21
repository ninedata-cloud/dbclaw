"""Add diagnosis timestamps and source event tracking to alert_event"""
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
                  AND table_name = 'alert_event'
                  AND column_name = :column_name
            )
            """
        ),
        {"column_name": column_name},
    )
    return bool(result.scalar_one())


async def migrate():
    """Add diagnosis_started_at, diagnosis_completed_at, diagnosis_source_event_id to alert_event"""
    async with engine.begin() as conn:
        if not await _column_exists(conn, "diagnosis_started_at"):
            await conn.execute(text("ALTER TABLE alert_event ADD COLUMN diagnosis_started_at TIMESTAMPTZ"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_alert_event_diagnosis_started_at "
                "ON alert_event(diagnosis_started_at)"
            ))
            logger.info("Added diagnosis_started_at column to alert_event")
        else:
            logger.info("Column diagnosis_started_at already exists, skipping")

        if not await _column_exists(conn, "diagnosis_completed_at"):
            await conn.execute(text("ALTER TABLE alert_event ADD COLUMN diagnosis_completed_at TIMESTAMPTZ"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_alert_event_diagnosis_completed_at "
                "ON alert_event(diagnosis_completed_at)"
            ))
            await conn.execute(text(
                "UPDATE alert_event "
                "SET diagnosis_completed_at = COALESCE(updated_at, event_ended_at, event_started_at) "
                "WHERE diagnosis_status = 'completed' AND diagnosis_completed_at IS NULL"
            ))
            logger.info("Added diagnosis_completed_at column to alert_event")
        else:
            logger.info("Column diagnosis_completed_at already exists, skipping")

        if not await _column_exists(conn, "diagnosis_source_event_id"):
            await conn.execute(text("ALTER TABLE alert_event ADD COLUMN diagnosis_source_event_id INTEGER"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_alert_event_diagnosis_source_event_id "
                "ON alert_event(diagnosis_source_event_id)"
            ))
            logger.info("Added diagnosis_source_event_id column to alert_event")
        else:
            logger.info("Column diagnosis_source_event_id already exists, skipping")


if __name__ == "__main__":
    asyncio.run(migrate())
