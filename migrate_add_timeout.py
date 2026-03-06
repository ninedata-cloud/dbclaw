"""
Database migration: Add timeout column to skills table

This migration adds support for per-skill execution timeouts.
"""
import sqlite3
import sys
from pathlib import Path


def migrate():
    """Add timeout column to skills table"""
    db_path = Path(__file__).parent / "data" / "smartdba.db"

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Migration will be applied when database is created.")
        return 0

    print(f"Migrating database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(skills)")
        columns = [row[1] for row in cursor.fetchall()]

        if "timeout" in columns:
            print("✓ Column 'timeout' already exists in skills table")
            conn.close()
            return 0

        # Add timeout column
        print("Adding 'timeout' column to skills table...")
        cursor.execute("""
            ALTER TABLE skills
            ADD COLUMN timeout INTEGER
        """)

        conn.commit()
        print("✓ Migration completed successfully")

        # Verify
        cursor.execute("PRAGMA table_info(skills)")
        columns = [row[1] for row in cursor.fetchall()]

        if "timeout" in columns:
            print("✓ Verified: Column 'timeout' exists")
        else:
            print("✗ Error: Column 'timeout' not found after migration")
            conn.close()
            return 1

        conn.close()
        return 0

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = migrate()
    sys.exit(exit_code)
