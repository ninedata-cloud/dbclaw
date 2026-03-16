"""
Migration: Rename connection_id to datasource_id in metric_snapshots table
"""
from sqlalchemy import text


def migrate(connection):
    """Rename connection_id to datasource_id in metric_snapshots table"""

    # Check if metric_snapshots table exists
    result = connection.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'metric_snapshots'
    """))
    if not result.fetchone():
        print("metric_snapshots table does not exist, skipping migration")
        return

    # Check if datasource_id already exists
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'metric_snapshots' AND column_name = 'datasource_id'
    """))
    if result.fetchone():
        print("metric_snapshots table already has datasource_id column, skipping migration")
        return

    # Check if connection_id exists
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'metric_snapshots' AND column_name = 'connection_id'
    """))
    if not result.fetchone():
        print("metric_snapshots table does not have connection_id column, skipping migration")
        return

    print("Migrating metric_snapshots table: connection_id -> datasource_id")
    connection.execute(text("""
        ALTER TABLE metric_snapshots RENAME COLUMN connection_id TO datasource_id
    """))
    print("metric_snapshots table migration completed successfully")
