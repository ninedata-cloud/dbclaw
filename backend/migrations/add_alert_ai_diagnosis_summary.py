"""Add ai_diagnosis_summary to alert_events table"""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def migrate():
    """Add ai_diagnosis_summary column to alert_events"""
    async with engine.begin() as conn:
        # Check if column already exists
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='alert_events' AND column_name='ai_diagnosis_summary'"))
        if result.scalar_one_or_none():
            print("Column ai_diagnosis_summary already exists, skipping")
            return

        await conn.execute(text("ALTER TABLE alert_events ADD COLUMN ai_diagnosis_summary TEXT"))
        print("Added ai_diagnosis_summary column to alert_events")