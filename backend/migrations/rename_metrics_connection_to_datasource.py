"""
Migration: Rename connection_id to datasource_id in metric_snapshots table
"""
from sqlalchemy import text


def migrate(connection):
    """Rename connection_id to datasource_id in metric_snapshots table"""

    # Check if metric_snapshots table exists
    result = connection.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='metric_snapshots'"
    ))
    if not result.fetchone():
        print("metric_snapshots table does not exist, skipping migration")
        return

    # Check if datasource_id already exists
    result = connection.execute(text("PRAGMA table_info(metric_snapshots)"))
    columns = {row[1] for row in result.fetchall()}

    if 'datasource_id' in columns:
        print("metric_snapshots table already has datasource_id column, skipping migration")
        return

    if 'connection_id' not in columns:
        print("metric_snapshots table does not have connection_id column, skipping migration")
        return

    print("Migrating metric_snapshots table: connection_id -> datasource_id")

    # Create new table with correct schema
    connection.execute(text("""
        CREATE TABLE metric_snapshots_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datasource_id INTEGER NOT NULL,
            metric_type VARCHAR(50) NOT NULL,
            data JSON NOT NULL,
            collected_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Create indexes
    connection.execute(text("""
        CREATE INDEX ix_metric_snapshots_new_datasource_id
        ON metric_snapshots_new(datasource_id)
    """))
    connection.execute(text("""
        CREATE INDEX ix_metric_snapshots_new_collected_at
        ON metric_snapshots_new(collected_at)
    """))

    # Copy data
    connection.execute(text("""
        INSERT INTO metric_snapshots_new (
            id, datasource_id, metric_type, data, collected_at
        )
        SELECT
            id, connection_id, metric_type, data, collected_at
        FROM metric_snapshots
    """))

    # Drop old table
    connection.execute(text("DROP TABLE metric_snapshots"))

    # Rename new table
    connection.execute(text("ALTER TABLE metric_snapshots_new RENAME TO metric_snapshots"))

    print("metric_snapshots table migration completed successfully")
