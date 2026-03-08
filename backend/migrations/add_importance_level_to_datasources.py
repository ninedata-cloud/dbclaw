"""
Add importance_level and monitoring_interval to datasources table
Migration: 2026-03-07
"""
import sqlite3
import os


def migrate():
    db_path = os.path.join(os.path.dirname(__file__), '../../data/smartdba.db')

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(datasources)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'importance_level' not in columns:
            print("Adding importance_level column...")
            cursor.execute("""
                ALTER TABLE datasources
                ADD COLUMN importance_level VARCHAR(20) DEFAULT 'production'
            """)
            print("✅ importance_level column added")
        else:
            print("⏭️  importance_level column already exists")

        if 'monitoring_interval' not in columns:
            print("Adding monitoring_interval column...")
            cursor.execute("""
                ALTER TABLE datasources
                ADD COLUMN monitoring_interval INTEGER DEFAULT 60
            """)
            print("✅ monitoring_interval column added")
        else:
            print("⏭️  monitoring_interval column already exists")

        conn.commit()
        print("✅ Migration completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
