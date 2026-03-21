"""Add is_encrypted column to system_configs table"""
import asyncio
from sqlalchemy import text
from backend.database import async_session


async def migrate():
    async with async_session() as db:
        # Check if column already exists
        result = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'system_configs' AND column_name = 'is_encrypted'
        """))
        if result.scalar_one_or_none():
            print("Column is_encrypted already exists in system_configs")
            return

        await db.execute(text("""
            ALTER TABLE system_configs ADD COLUMN is_encrypted BOOLEAN DEFAULT FALSE
        """))
        await db.commit()
        print("Successfully added is_encrypted column to system_configs")


if __name__ == "__main__":
    asyncio.run(migrate())
