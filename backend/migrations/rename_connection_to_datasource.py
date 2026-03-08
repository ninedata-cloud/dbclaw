"""
Migration: Rename 'connections' table to 'datasources' and update foreign keys
"""
from sqlalchemy import text, inspect


def migrate(connection):
    """
    Rename connections table to datasources and update related columns.
    SQLite doesn't support direct table/column renames, so we need to recreate tables.
    """
    insp = inspect(connection)

    # Check if migration already applied
    if "datasources" in insp.get_table_names():
        # Check if diagnostic_sessions still has connection_id
        if "diagnostic_sessions" in insp.get_table_names():
            columns = [c["name"] for c in insp.get_columns("diagnostic_sessions")]
            if "connection_id" in columns and "datasource_id" not in columns:
                print("Datasources table exists but diagnostic_sessions needs update")
                # Only update diagnostic_sessions
                _update_diagnostic_sessions(connection, insp)
                return
        print("Migration already applied: datasources table exists")
        return

    if "connections" not in insp.get_table_names():
        print("No connections table to migrate")
        return

    print("Starting migration: connections -> datasources")

    # Step 1: Rename connections table to datasources
    connection.execute(text("ALTER TABLE connections RENAME TO datasources"))
    print("✓ Renamed connections table to datasources")

    # Step 2: Update diagnostic_sessions table if it exists
    _update_diagnostic_sessions(connection, insp)

    print("Migration completed successfully")


def _update_diagnostic_sessions(connection, insp):
    """Helper function to update diagnostic_sessions table"""
    if "diagnostic_sessions" not in insp.get_table_names():
        return

    columns = [c["name"] for c in insp.get_columns("diagnostic_sessions")]

    if "connection_id" not in columns:
        print("✓ diagnostic_sessions already updated")
        return

    # Get all column names to preserve them
    all_columns = [c["name"] for c in insp.get_columns("diagnostic_sessions")]

    # SQLite doesn't support ALTER COLUMN RENAME, so we need to recreate the table
    connection.execute(text("""
        CREATE TABLE diagnostic_sessions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datasource_id INTEGER,
            title VARCHAR(200),
            ai_model_id INTEGER,
            kb_ids TEXT,
            disabled_tools TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (datasource_id) REFERENCES datasources(id),
            FOREIGN KEY (ai_model_id) REFERENCES ai_models(id)
        )
    """))

    # Build column list for INSERT
    select_columns = []
    insert_columns = []
    for col in all_columns:
        if col == "connection_id":
            select_columns.append("connection_id")
            insert_columns.append("datasource_id")
        elif col in ["id", "title", "ai_model_id", "kb_ids", "disabled_tools", "created_at", "updated_at"]:
            select_columns.append(col)
            insert_columns.append(col)

    # Copy data from old table
    connection.execute(text(f"""
        INSERT INTO diagnostic_sessions_new
        ({', '.join(insert_columns)})
        SELECT {', '.join(select_columns)}
        FROM diagnostic_sessions
    """))

    # Drop old table and rename new one
    connection.execute(text("DROP TABLE diagnostic_sessions"))
    connection.execute(text("ALTER TABLE diagnostic_sessions_new RENAME TO diagnostic_sessions"))
    print("✓ Updated diagnostic_sessions: connection_id -> datasource_id")


