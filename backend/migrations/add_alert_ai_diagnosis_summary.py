"""Add ai_diagnosis_summary to alert_event table"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    """Add ai_diagnosis_summary column to alert_event"""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name='alert_event' AND column_name='ai_diagnosis_summary'"
                ")"
            )
        )
        if result.scalar_one():
            logger.info("Column ai_diagnosis_summary already exists, skipping")
            return

        await conn.execute(text("ALTER TABLE alert_event ADD COLUMN ai_diagnosis_summary TEXT"))
        logger.info("Added ai_diagnosis_summary column to alert_event")
