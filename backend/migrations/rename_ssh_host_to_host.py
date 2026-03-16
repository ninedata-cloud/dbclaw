"""Rename ssh_host_id to host_id and ssh_hosts table to hosts"""
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
            # Check if datasources has ssh_host_id
            result = await db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'datasources' AND column_name = 'ssh_host_id'
            """))
            if result.fetchone():
                print("Renaming ssh_host_id to host_id in datasources table...")
                await db.execute(text("ALTER TABLE datasources RENAME COLUMN ssh_host_id TO host_id"))
                print("Renamed ssh_host_id to host_id in datasources")
            else:
                print("Column ssh_host_id already renamed or doesn't exist")

            # Check if ssh_hosts table exists
            result = await db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'ssh_hosts'
            """))
            if result.fetchone():
                print("Renaming ssh_hosts table to hosts...")
                await db.execute(text("ALTER TABLE ssh_hosts RENAME TO hosts"))
                print("Renamed ssh_hosts table to hosts")
            else:
                print("Table ssh_hosts already renamed or doesn't exist")

            # Check if host_metrics table has ssh_host_id
            result = await db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'host_metrics'
            """))
            if result.fetchone():
                result = await db.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'host_metrics' AND column_name = 'ssh_host_id'
                """))
                if result.fetchone():
                    print("Renaming ssh_host_id to host_id in host_metrics table...")
                    await db.execute(text("ALTER TABLE host_metrics RENAME COLUMN ssh_host_id TO host_id"))
                    print("Renamed ssh_host_id to host_id in host_metrics")

            await db.commit()
            print("Migration completed successfully!")

        except Exception as e:
            await db.rollback()
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(migrate())
