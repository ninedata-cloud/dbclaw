"""Add performance indexes to reports table"""
import sqlite3
import logging

logger = logging.getLogger(__name__)

def migrate():
    """Add indexes to reports table for better query performance"""
    db_path = "data/smartdba.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check existing indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reports'")
        existing_indexes = {row[0] for row in cursor.fetchall()}
        
        indexes_to_create = [
            ("idx_reports_datasource_id", "CREATE INDEX IF NOT EXISTS idx_reports_datasource_id ON reports(datasource_id)"),
            ("idx_reports_status", "CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)"),
            ("idx_reports_trigger_type", "CREATE INDEX IF NOT EXISTS idx_reports_trigger_type ON reports(trigger_type)"),
            ("idx_reports_created_at", "CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC)"),
            ("idx_reports_composite", "CREATE INDEX IF NOT EXISTS idx_reports_composite ON reports(datasource_id, status, trigger_type, created_at DESC)")
        ]
        
        for idx_name, sql in indexes_to_create:
            if idx_name not in existing_indexes:
                logger.info(f"Creating index: {idx_name}")
                cursor.execute(sql)
                print(f"✓ Created index: {idx_name}")
            else:
                print(f"- Index already exists: {idx_name}")
        
        conn.commit()
        print("\n✓ All indexes created successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
