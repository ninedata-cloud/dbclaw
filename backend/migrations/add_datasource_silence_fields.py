"""
Add silence fields to datasource table
为数据源表添加临时静默字段

Usage:
    python backend/migrations/add_datasource_silence_fields.py
"""
import asyncio
from sqlalchemy import text
from backend.database import async_session


async def migrate():
    """Add silence_until and silence_reason columns to datasource table"""
    async with async_session() as db:
        try:
            # Check if columns already exist
            result = await db.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'datasource'
                AND column_name IN ('silence_until', 'silence_reason')
            """))
            existing_columns = {row[0] for row in result.fetchall()}

            # Add silence_until column if not exists
            if 'silence_until' not in existing_columns:
                await db.execute(text("""
                    ALTER TABLE datasource
                    ADD COLUMN silence_until TIMESTAMP NULL
                """))
                print("✓ Added column: silence_until")
            else:
                print("- Column already exists: silence_until")

            # Add silence_reason column if not exists
            if 'silence_reason' not in existing_columns:
                await db.execute(text("""
                    ALTER TABLE datasource
                    ADD COLUMN silence_reason VARCHAR(500) NULL
                """))
                print("✓ Added column: silence_reason")
            else:
                print("- Column already exists: silence_reason")

            await db.commit()
            print("\n✓ Migration completed successfully")

        except Exception as e:
            await db.rollback()
            print(f"\n✗ Migration failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(migrate())
