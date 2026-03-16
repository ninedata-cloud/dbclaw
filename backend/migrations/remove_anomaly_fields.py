"""Migration: Remove anomaly-related fields from inspection_configs table"""
from sqlalchemy import text


def migrate(connection):
    """Remove anomaly fields from inspection_configs table"""
    try:
        # PostgreSQL supports DROP COLUMN directly
        cols_to_drop = ['anomaly_check_enabled', 'anomaly_diagnosis_interval', 'last_anomaly_diagnosis_at']
        for col in cols_to_drop:
            result = connection.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'inspection_configs' AND column_name = :col
            """), {"col": col})
            if result.fetchone():
                connection.execute(text(f"ALTER TABLE inspection_configs DROP COLUMN {col}"))

        # Recreate index if needed
        result = connection.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'inspection_configs' AND indexname = 'ix_inspection_configs_id'
        """))
        if not result.fetchone():
            connection.execute(text("CREATE INDEX ix_inspection_configs_id ON inspection_configs (id)"))

        print("Removed anomaly fields from inspection_configs table")
    except Exception as e:
        print(f"Migration already applied or error: {e}")
