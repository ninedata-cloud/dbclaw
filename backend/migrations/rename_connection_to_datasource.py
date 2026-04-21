"""
Migration: Rename 'connections' table to 'datasource' and update foreign keys
"""
from sqlalchemy import text, inspect


def migrate(connection):
    """
    Rename connections table to datasource and update related columns.
    PostgreSQL supports direct RENAME TABLE and RENAME COLUMN.
    """
    insp = inspect(connection)

    # Check if migration already applied
    if "datasource" in insp.get_table_names():
        if "diagnostic_session" in insp.get_table_names():
            columns = [c["name"] for c in insp.get_columns("diagnostic_session")]
            if "connection_id" in columns and "datasource_id" not in columns:
                print("Datasources table exists but diagnostic_session needs update")
                _update_diagnostic_session(connection)
                return
        print("Migration already applied: datasource table exists")
        return

    if "connections" not in insp.get_table_names():
        print("No connections table to migrate")
        return

    print("Starting migration: connections -> datasource")

    # Rename connections table to datasource
    connection.execute(text("ALTER TABLE connections RENAME TO datasource"))
    print("Renamed connections table to datasource")

    # Update diagnostic_session table if it exists
    _update_diagnostic_session(connection)

    print("Migration completed successfully")


def _update_diagnostic_session(connection):
    """Helper function to update diagnostic_session table"""
    result = connection.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'diagnostic_session' AND column_name = 'connection_id'
    """))
    if not result.fetchone():
        print("diagnostic_session already updated")
        return

    connection.execute(text("""
        ALTER TABLE diagnostic_session RENAME COLUMN connection_id TO datasource_id
    """))
    print("Updated diagnostic_session: connection_id -> datasource_id")
