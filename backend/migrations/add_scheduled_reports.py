"""
Migration: Add scheduled reports functionality

This migration adds three new tables for scheduled report generation:
1. scheduled_report_configs - Configuration for each datasource's scheduled reports
2. scheduled_report_history - Audit trail of all scheduled report generations
3. Extends reports table with scheduled report columns
"""

from sqlalchemy import text
from backend.database import engine
import logging

logger = logging.getLogger(__name__)


async def upgrade():
    """Apply the migration"""
    async with engine.begin() as conn:
        # Check if scheduled_report_configs table exists
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_report_configs'")
        )
        if result.fetchone() is None:
            logger.info("Creating scheduled_report_configs table...")
            await conn.execute(text("""
                CREATE TABLE scheduled_report_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    datasource_id INTEGER NOT NULL UNIQUE,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    report_type VARCHAR(50) NOT NULL DEFAULT 'comprehensive',
                    schedule_interval INTEGER NOT NULL,
                    use_ai_analysis BOOLEAN NOT NULL DEFAULT 0,
                    ai_model_id INTEGER,
                    kb_ids TEXT,
                    last_generated_at TIMESTAMP,
                    next_scheduled_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                    FOREIGN KEY (ai_model_id) REFERENCES ai_models(id) ON DELETE SET NULL
                )
            """))
            logger.info("Created scheduled_report_configs table")

        # Check if scheduled_report_history table exists
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_report_history'")
        )
        if result.fetchone() is None:
            logger.info("Creating scheduled_report_history table...")
            await conn.execute(text("""
                CREATE TABLE scheduled_report_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    report_id INTEGER,
                    datasource_id INTEGER NOT NULL,
                    scheduled_time TIMESTAMP NOT NULL,
                    actual_generation_time TIMESTAMP,
                    generation_duration_seconds REAL,
                    status VARCHAR(20) NOT NULL,
                    skip_reason TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES scheduled_report_configs(id) ON DELETE CASCADE,
                    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE SET NULL,
                    FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE
                )
            """))
            logger.info("Created scheduled_report_history table")

        # Check if reports table has is_scheduled column
        result = await conn.execute(text("PRAGMA table_info(reports)"))
        columns = [row[1] for row in result.fetchall()]

        if 'is_scheduled' not in columns:
            logger.info("Adding is_scheduled column to reports table...")
            await conn.execute(text("ALTER TABLE reports ADD COLUMN is_scheduled BOOLEAN DEFAULT 0"))
            logger.info("Added is_scheduled column")

        if 'schedule_config_id' not in columns:
            logger.info("Adding schedule_config_id column to reports table...")
            await conn.execute(text("ALTER TABLE reports ADD COLUMN schedule_config_id INTEGER"))
            logger.info("Added schedule_config_id column")

        if 'retention_days' not in columns:
            logger.info("Adding retention_days column to reports table...")
            await conn.execute(text("ALTER TABLE reports ADD COLUMN retention_days INTEGER DEFAULT 30"))
            logger.info("Added retention_days column")

        # Create indexes for performance
        logger.info("Creating indexes...")

        # Index for finding next scheduled reports
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_configs_next_time
            ON scheduled_report_configs(next_scheduled_at)
        """))

        # Index for history queries by datasource
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_history_datasource
            ON scheduled_report_history(datasource_id, created_at)
        """))

        # Index for filtering scheduled reports
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reports_scheduled
            ON reports(is_scheduled, created_at)
        """))

        logger.info("Indexes created successfully")
        logger.info("Migration completed successfully")


async def downgrade():
    """Rollback the migration"""
    async with engine.begin() as conn:
        logger.info("Rolling back scheduled reports migration...")

        # Drop indexes
        await conn.execute(text("DROP INDEX IF EXISTS idx_scheduled_configs_next_time"))
        await conn.execute(text("DROP INDEX IF EXISTS idx_scheduled_history_datasource"))
        await conn.execute(text("DROP INDEX IF EXISTS idx_reports_scheduled"))

        # Drop tables
        await conn.execute(text("DROP TABLE IF EXISTS scheduled_report_history"))
        await conn.execute(text("DROP TABLE IF EXISTS scheduled_report_configs"))

        # Note: SQLite doesn't support DROP COLUMN, so we can't remove columns from reports table
        logger.info("Rollback completed (note: columns in reports table remain)")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()

    asyncio.run(main())
