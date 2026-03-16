"""
Migration: Rename connection_id to datasource_id in reports table
"""
from sqlalchemy import text


def migrate(connection):
    """Rename connection_id to datasource_id in reports table"""

    # Check if reports table exists
    result = connection.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'reports'
    """))
    if not result.fetchone():
        print("Reports table does not exist, skipping migration")
        return

    # Check if datasource_id already exists
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'reports' AND column_name = 'datasource_id'
    """))
    if result.fetchone():
        print("Reports table already has datasource_id column, skipping migration")
        return

    # Check if connection_id exists
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'reports' AND column_name = 'connection_id'
    """))
    if not result.fetchone():
        print("Reports table does not have connection_id column, skipping migration")
        return

    print("Migrating reports table: connection_id -> datasource_id")
    connection.execute(text("""
        ALTER TABLE reports RENAME COLUMN connection_id TO datasource_id
    """))
    print("Reports table migration completed successfully")
