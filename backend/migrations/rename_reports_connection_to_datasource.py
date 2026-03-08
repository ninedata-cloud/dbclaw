"""
Migration: Rename connection_id to datasource_id in reports table
"""
from sqlalchemy import text


def migrate(connection):
    """Rename connection_id to datasource_id in reports table"""

    # Check if reports table exists and has connection_id column
    result = connection.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reports'"
    ))
    if not result.fetchone():
        print("Reports table does not exist, skipping migration")
        return

    # Check if datasource_id already exists
    result = connection.execute(text("PRAGMA table_info(reports)"))
    columns = {row[1] for row in result.fetchall()}

    if 'datasource_id' in columns:
        print("Reports table already has datasource_id column, skipping migration")
        return

    if 'connection_id' not in columns:
        print("Reports table does not have connection_id column, skipping migration")
        return

    print("Migrating reports table: connection_id -> datasource_id")

    # SQLite doesn't support RENAME COLUMN directly in older versions
    # We need to recreate the table

    # 1. Create new table with correct schema
    connection.execute(text("""
        CREATE TABLE reports_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datasource_id INTEGER NOT NULL,
            title VARCHAR(200) NOT NULL,
            report_type VARCHAR(50) DEFAULT 'comprehensive',
            status VARCHAR(20) DEFAULT 'generating',
            summary TEXT,
            content_md TEXT,
            content_html TEXT,
            findings JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """))

    # 2. Copy data from old table to new table
    connection.execute(text("""
        INSERT INTO reports_new (
            id, datasource_id, title, report_type, status,
            summary, content_md, content_html, findings,
            created_at, completed_at
        )
        SELECT
            id, connection_id, title, report_type, status,
            summary, content_md, content_html, findings,
            created_at, completed_at
        FROM reports
    """))

    # 3. Drop old table
    connection.execute(text("DROP TABLE reports"))

    # 4. Rename new table to original name
    connection.execute(text("ALTER TABLE reports_new RENAME TO reports"))

    print("Reports table migration completed successfully")
