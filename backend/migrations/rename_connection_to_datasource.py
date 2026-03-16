"""
Migration: Rename 'connections' table to 'datasources' and update foreign keys
"""
from sqlalchemy import text, inspect


def migrate(connection):
    """
    Rename connections table to datasources and update related columns.
    PostgreSQL supports direct RENAME TABLE and RENAME COLUMN.
    """
    insp = inspect(connection)

    # Check if migration already applied
    if "datasources" in insp.get_table_names():
        if "diagnostic_sessions" in insp.get_table_names():
            columns = [c["name"] for c in insp.get_columns("diagnostic_sessions")]
            if "connection_id" in columns and "datasource_id" not in columns:
                print("Datasources table exists but diagnostic_sessions needs update")
                _update_diagnostic_sessions(connection)
                return
        print("Migration already applied: datasources table exists")
        return

    if "connections" not in insp.get_table_names():
        print("No connections table to migrate")
        return

    print("Starting migration: connections -> datasources")

    # Rename connections table to datasources
    connection.execute(text("ALTER TABLE connections RENAME TO datasources"))
    print("Renamed connections table to datasources")

    # Update diagnostic_sessions table if it exists
    _update_diagnostic_sessions(connection)

    print("Migration completed successfully")


def _update_diagnostic_sessions(connection):
    """Helper function to update diagnostic_sessions table"""
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'diagnostic_sessions' AND column_name = 'connection_id'
    """))
    if not result.fetchone():
        print("diagnostic_sessions already updated")
        return

    connection.execute(text("""
        ALTER TABLE diagnostic_sessions RENAME COLUMN connection_id TO datasource_id
    """))
    print("Updated diagnostic_sessions: connection_id -> datasource_id")
