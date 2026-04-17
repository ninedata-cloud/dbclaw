"""Add diagnosis timestamps and source event tracking to alert_events"""
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
    """Add diagnosis_started_at, diagnosis_completed_at, diagnosis_source_event_id to alert_events"""
    async with engine.begin() as conn:
        if not await _column_exists(conn, "diagnosis_started_at"):
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN diagnosis_started_at TIMESTAMP"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_alert_events_diagnosis_started_at "
                "ON alert_events(diagnosis_started_at)"
            ))
            logger.info("Added diagnosis_started_at column to alert_events")
        else:
            logger.info("Column diagnosis_started_at already exists, skipping")

        if not await _column_exists(conn, "diagnosis_completed_at"):
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN diagnosis_completed_at TIMESTAMP"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_alert_events_diagnosis_completed_at "
                "ON alert_events(diagnosis_completed_at)"
            ))
            await conn.execute(text(
                "UPDATE alert_events "
                "SET diagnosis_completed_at = COALESCE(last_updated, event_end_time, event_start_time) "
                "WHERE diagnosis_status = 'completed' AND diagnosis_completed_at IS NULL"
            ))
            logger.info("Added diagnosis_completed_at column to alert_events")
        else:
            logger.info("Column diagnosis_completed_at already exists, skipping")

        if not await _column_exists(conn, "diagnosis_source_event_id"):
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN diagnosis_source_event_id INTEGER"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_alert_events_diagnosis_source_event_id "
                "ON alert_events(diagnosis_source_event_id)"
            ))
            logger.info("Added diagnosis_source_event_id column to alert_events")
        else:
            logger.info("Column diagnosis_source_event_id already exists, skipping")


if __name__ == "__main__":
    asyncio.run(migrate())
