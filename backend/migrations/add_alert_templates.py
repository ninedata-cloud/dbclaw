"""
Migration: add alert template table and inspection config binding column.
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
            "WHERE table_schema = current_schema() "
            "AND table_name = :table_name AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none() is not None


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alert_templates (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(120) NOT NULL UNIQUE,
                    description TEXT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    template_config JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_templates_enabled "
                "ON alert_templates (enabled)"
            )
        )
        if not await _column_exists(conn, "inspection_configs", "alert_template_id"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN alert_template_id INTEGER NULL"
                )
            )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_inspection_configs_alert_template_id "
                "ON inspection_configs (alert_template_id)"
            )
        )
        logger.info("Migration complete: alert template table and inspection binding column added")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
