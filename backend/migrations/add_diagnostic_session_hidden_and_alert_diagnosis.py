"""Add is_hidden and ai_diagnosis_summary columns"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar_one())


async def migrate():
    """Add is_hidden to diagnostic_session and ai_diagnosis_summary to alert_event"""
    async with engine.begin() as conn:
        if not await _column_exists(conn, "diagnostic_session", "is_hidden"):
            await conn.execute(text("ALTER TABLE diagnostic_session ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE"))
            logger.info("Added is_hidden column to diagnostic_session")

        if not await _column_exists(conn, "alert_event", "ai_diagnosis_summary"):
            await conn.execute(text("ALTER TABLE alert_event ADD COLUMN ai_diagnosis_summary TEXT"))
            logger.info("Added ai_diagnosis_summary column to alert_event")

    logger.info("Migration complete: diagnostic_session.is_hidden + alert_event.ai_diagnosis_summary")
