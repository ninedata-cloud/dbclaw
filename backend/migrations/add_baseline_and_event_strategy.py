"""
Migration: add baseline config/profile tables and event strategy metadata.
"""

import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table_name AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none() is not None


async def migrate():
    async with engine.begin() as conn:
        inspection_columns = [
            ("baseline_config", "ALTER TABLE inspection_configs ADD COLUMN baseline_config JSONB NOT NULL DEFAULT '{}'::jsonb"),
            ("event_ai_config", "ALTER TABLE inspection_configs ADD COLUMN event_ai_config JSONB NOT NULL DEFAULT '{}'::jsonb"),
        ]
        for column_name, ddl in inspection_columns:
            if not await _column_exists(conn, "inspection_configs", column_name):
                await conn.execute(text(ddl))

        event_columns = [
            ("event_category", "ALTER TABLE alert_events ADD COLUMN event_category VARCHAR(50) NULL"),
            ("fault_domain", "ALTER TABLE alert_events ADD COLUMN fault_domain VARCHAR(50) NULL"),
            ("lifecycle_stage", "ALTER TABLE alert_events ADD COLUMN lifecycle_stage VARCHAR(30) NULL"),
            ("diagnosis_refresh_needed", "ALTER TABLE alert_events ADD COLUMN diagnosis_refresh_needed BOOLEAN NOT NULL DEFAULT TRUE"),
            ("diagnosis_trigger_reason", "ALTER TABLE alert_events ADD COLUMN diagnosis_trigger_reason VARCHAR(50) NULL"),
            ("last_diagnosed_severity", "ALTER TABLE alert_events ADD COLUMN last_diagnosed_severity VARCHAR(20) NULL"),
            ("last_diagnosed_alert_count", "ALTER TABLE alert_events ADD COLUMN last_diagnosed_alert_count INTEGER NULL"),
            ("last_diagnosis_requested_at", "ALTER TABLE alert_events ADD COLUMN last_diagnosis_requested_at TIMESTAMP NULL"),
        ]
        for column_name, ddl in event_columns:
            if not await _column_exists(conn, "alert_events", column_name):
                await conn.execute(text(ddl))

        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS metric_baseline_profiles (
                    id SERIAL PRIMARY KEY,
                    datasource_id INTEGER NOT NULL,
                    metric_name VARCHAR(100) NOT NULL,
                    weekday INTEGER NOT NULL,
                    hour INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    avg_value DOUBLE PRECISION NULL,
                    min_value DOUBLE PRECISION NULL,
                    max_value DOUBLE PRECISION NULL,
                    p50_value DOUBLE PRECISION NULL,
                    p95_value DOUBLE PRECISION NULL,
                    stddev_value DOUBLE PRECISION NULL,
                    last_snapshot_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_metric_baseline_profile_slot UNIQUE (datasource_id, metric_name, weekday, hour)
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_metric_baseline_profiles_datasource_metric "
                "ON metric_baseline_profiles (datasource_id, metric_name)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_events_fault_domain "
                "ON alert_events (fault_domain)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_events_event_category "
                "ON alert_events (event_category)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_events_diagnosis_refresh_needed "
                "ON alert_events (diagnosis_refresh_needed)"
            )
        )

        logger.info("Migration complete: baseline profiles and event strategy metadata added")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
