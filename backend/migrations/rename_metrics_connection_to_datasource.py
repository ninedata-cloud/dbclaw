"""
Migration: Rename connection_id to datasource_id in datasource_metric table
"""
from sqlalchemy import text


def migrate(connection):
    """Rename connection_id to datasource_id in datasource_metric table"""

    # Check if datasource_metric table exists
    result = connection.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'datasource_metric'
    """))
    if not result.fetchone():
        print("datasource_metric table does not exist, skipping migration")
        return

    # Check if datasource_id already exists
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'datasource_metric' AND column_name = 'datasource_id'
    """))
    if result.fetchone():
        print("datasource_metric table already has datasource_id column, skipping migration")
        return

    # Check if connection_id exists
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'datasource_metric' AND column_name = 'connection_id'
    """))
    if not result.fetchone():
        print("datasource_metric table does not have connection_id column, skipping migration")
        return

    print("Migrating datasource_metric table: connection_id -> datasource_id")
    connection.execute(text("""
        ALTER TABLE datasource_metric RENAME COLUMN connection_id TO datasource_id
    """))
    print("datasource_metric table migration completed successfully")
