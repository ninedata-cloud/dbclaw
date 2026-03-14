"""Add AI inspection fields to reports table"""
import asyncio
from sqlalchemy import text
from backend.database import async_session


async def migrate():
    """Add skill_executions and ai_conversation_id fields to reports table"""
    async with async_session() as db:
        # Check if columns already exist
        result = await db.execute(text("PRAGMA table_info(reports)"))
        columns = [row[1] for row in result.fetchall()]

        if 'skill_executions' not in columns:
            await db.execute(text("ALTER TABLE reports ADD COLUMN skill_executions TEXT"))
            print("Added skill_executions column")

        if 'ai_conversation_id' not in columns:
            await db.execute(text("ALTER TABLE reports ADD COLUMN ai_conversation_id INTEGER"))
            print("Added ai_conversation_id column")

        await db.commit()
        print("Migration completed successfully")


if __name__ == "__main__":
    asyncio.run(migrate())
