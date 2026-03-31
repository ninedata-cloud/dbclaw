"""Add root_cause, recommended_actions, diagnosis_status to alert_events table"""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def migrate():
    """Add diagnosis fields to alert_events"""
    async with engine.begin() as conn:
        # Check if root_cause column already exists
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='alert_events' AND column_name='root_cause'"
        ))
        if not result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN root_cause TEXT"))
            print("Added root_cause column to alert_events")
        else:
            print("Column root_cause already exists, skipping")

        # Check if recommended_actions column already exists
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='alert_events' AND column_name='recommended_actions'"
        ))
        if not result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN recommended_actions TEXT"))
            print("Added recommended_actions column to alert_events")
        else:
            print("Column recommended_actions already exists, skipping")

        # Check if diagnosis_status column already exists
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='alert_events' AND column_name='diagnosis_status'"
        ))
        if not result.scalar_one_or_none():
            await conn.execute(text("ALTER TABLE alert_events ADD COLUMN diagnosis_status VARCHAR(20)"))
            print("Added diagnosis_status column to alert_events")
        else:
            print("Column diagnosis_status already exists, skipping")


if __name__ == "__main__":
    asyncio.run(migrate())
