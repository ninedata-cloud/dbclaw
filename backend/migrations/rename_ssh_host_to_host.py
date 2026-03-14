"""Rename ssh_host_id to host_id and ssh_hosts table to hosts"""
import sqlite3
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_settings

def migrate():
    settings = get_settings()
    db_path = settings.database_url.replace('sqlite+aiosqlite:///', '')

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if migration is needed
        cursor.execute("PRAGMA table_info(datasources)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'ssh_host_id' in columns:
            print("Renaming ssh_host_id to host_id in datasources table...")
            cursor.execute("ALTER TABLE datasources RENAME COLUMN ssh_host_id TO host_id")
            print("✓ Renamed ssh_host_id to host_id in datasources")
        else:
            print("Column ssh_host_id already renamed or doesn't exist")

        # Check if ssh_hosts table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ssh_hosts'")
        if cursor.fetchone():
            print("Renaming ssh_hosts table to hosts...")
            cursor.execute("ALTER TABLE ssh_hosts RENAME TO hosts")
            print("✓ Renamed ssh_hosts table to hosts")
        else:
            print("Table ssh_hosts already renamed or doesn't exist")

        # Check if host_metrics table has ssh_host_id
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='host_metrics'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(host_metrics)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'ssh_host_id' in columns:
                print("Renaming ssh_host_id to host_id in host_metrics table...")
                cursor.execute("ALTER TABLE host_metrics RENAME COLUMN ssh_host_id TO host_id")
                print("✓ Renamed ssh_host_id to host_id in host_metrics")

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
