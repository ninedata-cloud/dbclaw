"""Migration: Remove anomaly-related fields from inspection_config table"""
from sqlalchemy import text


def migrate(connection):
    """Remove anomaly fields from inspection_config table"""
    try:
        # PostgreSQL supports DROP COLUMN directly
        cols_to_drop = ['anomaly_check_enabled', 'anomaly_diagnosis_interval', 'last_anomaly_diagnosis_at']
        for col in cols_to_drop:
            result = connection.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'inspection_config' AND column_name = :col
            """), {"col": col})
            if result.fetchone():
                connection.execute(text(f"ALTER TABLE inspection_config DROP COLUMN {col}"))

        # Recreate index if needed
        result = connection.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'inspection_config' AND indexname = 'ix_inspection_config_id'
        """))
        if not result.fetchone():
            connection.execute(text("CREATE INDEX ix_inspection_config_id ON inspection_config (id)"))

        print("Removed anomaly fields from inspection_config table")
    except Exception as e:
        print(f"Migration already applied or error: {e}")
