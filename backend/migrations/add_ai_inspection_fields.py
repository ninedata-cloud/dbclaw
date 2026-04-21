"""Add AI inspection fields to report table"""
import asyncio
from sqlalchemy import text
from backend.database import async_session


async def migrate():
    """Add skill_executions and ai_conversation_id fields to report table"""
    async with async_session() as db:
        # Check if columns already exist
        result = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'report' AND column_name IN ('skill_executions', 'ai_conversation_id')
        """))
        existing = {row[0] for row in result.fetchall()}

        if 'skill_executions' not in existing:
            await db.execute(text("ALTER TABLE report ADD COLUMN skill_executions TEXT"))
            print("Added skill_executions column")

        if 'ai_conversation_id' not in existing:
            await db.execute(text("ALTER TABLE report ADD COLUMN ai_conversation_id INTEGER"))
            print("Added ai_conversation_id column")

        await db.commit()
        print("Migration completed successfully")


if __name__ == "__main__":
    asyncio.run(migrate())
