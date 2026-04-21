"""Rename ssh_host_id to host_id and ssh_host table to host"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.database import async_session


async def migrate():
    async with async_session() as db:
        try:
            # Check if datasource has ssh_host_id
            result = await db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'datasource' AND column_name = 'ssh_host_id'
            """))
            if result.fetchone():
                print("Renaming ssh_host_id to host_id in datasource table...")
                await db.execute(text("ALTER TABLE datasource RENAME COLUMN ssh_host_id TO host_id"))
                print("Renamed ssh_host_id to host_id in datasource")
            else:
                print("Column ssh_host_id already renamed or doesn't exist")

            # Check if ssh_host table exists
            result = await db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'ssh_host'
            """))
            if result.fetchone():
                print("Renaming ssh_host table to host...")
                await db.execute(text("ALTER TABLE ssh_host RENAME TO host"))
                print("Renamed ssh_host table to host")
            else:
                print("Table ssh_host already renamed or doesn't exist")

            # Check if host_metric table has ssh_host_id
            result = await db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'host_metric'
            """))
            if result.fetchone():
                result = await db.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'host_metric' AND column_name = 'ssh_host_id'
                """))
                if result.fetchone():
                    print("Renaming ssh_host_id to host_id in host_metric table...")
                    await db.execute(text("ALTER TABLE host_metric RENAME COLUMN ssh_host_id TO host_id"))
                    print("Renamed ssh_host_id to host_id in host_metric")

            await db.commit()
            print("Migration completed successfully!")

        except Exception as e:
            await db.rollback()
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(migrate())
