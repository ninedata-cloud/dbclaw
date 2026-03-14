"""Migration: Remove anomaly-related fields from inspection_configs table"""
from sqlalchemy import text


def migrate(connection):
    """Remove anomaly fields from inspection_configs table"""
    try:
        # SQLite doesn't support DROP COLUMN directly, need to recreate table
        connection.execute(text("""
            CREATE TABLE inspection_configs_new (
                id INTEGER NOT NULL,
                datasource_id INTEGER NOT NULL,
                enabled BOOLEAN NOT NULL,
                schedule_interval INTEGER NOT NULL,
                last_scheduled_at DATETIME,
                next_scheduled_at DATETIME,
                use_ai_analysis BOOLEAN NOT NULL,
                ai_model_id INTEGER,
                kb_ids JSON NOT NULL,
                threshold_rules JSON NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (datasource_id),
                FOREIGN KEY(datasource_id) REFERENCES datasources (id)
            )
        """))

        # Copy data from old table to new table (excluding anomaly fields)
        connection.execute(text("""
            INSERT INTO inspection_configs_new
            (id, datasource_id, enabled, schedule_interval, last_scheduled_at, next_scheduled_at,
             use_ai_analysis, ai_model_id, kb_ids, threshold_rules, created_at, updated_at)
            SELECT id, datasource_id, enabled, schedule_interval, last_scheduled_at, next_scheduled_at,
                   use_ai_analysis, ai_model_id, kb_ids, threshold_rules, created_at, updated_at
            FROM inspection_configs
        """))

        # Drop old table
        connection.execute(text("DROP TABLE inspection_configs"))

        # Rename new table
        connection.execute(text("ALTER TABLE inspection_configs_new RENAME TO inspection_configs"))

        # Recreate index
        connection.execute(text("CREATE INDEX ix_inspection_configs_id ON inspection_configs (id)"))

        print("✓ Removed anomaly fields from inspection_configs table")
    except Exception as e:
        print(f"Migration already applied or error: {e}")
