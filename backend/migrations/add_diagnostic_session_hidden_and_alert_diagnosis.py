"""Add is_hidden and ai_diagnosis_summary columns"""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def migrate():
    """Add is_hidden to diagnostic_sessions and ai_diagnosis_summary to alert_events"""
    async with engine.begin() as conn:
        # Check if is_hidden already exists
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='diagnostic_sessions' AND column_name='is_hidden'"))
        if not result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE"))
            print("Added is_hidden column to diagnostic_sessions")

        # Check if ai_diagnosis_summary already exists
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_events' AND column_name='ai_diagnosis_summary'"))
        if not result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN ai_diagnosis_summary TEXT"))
            print("Added ai_diagnosis_summary column to alert_events")

    print("Migration complete: diagnostic_sessions.is_hidden + alert_events.ai_diagnosis_summary")