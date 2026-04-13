"""
Migration: extend inspection_configs for dual alert engines.

New AI-specific tables are created by SQLAlchemy create_all once models are imported.
This migration only backfills columns on the existing inspection_configs table.
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
        if not await _column_exists(conn, "inspection_configs", "alert_engine_mode"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN alert_engine_mode VARCHAR(20) NOT NULL DEFAULT 'inherit'"
                )
            )

        if not await _column_exists(conn, "inspection_configs", "ai_policy_source"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN ai_policy_source VARCHAR(20) NOT NULL DEFAULT 'inline'"
                )
            )

        if not await _column_exists(conn, "inspection_configs", "ai_policy_text"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN ai_policy_text TEXT NULL"
                )
            )

        if not await _column_exists(conn, "inspection_configs", "ai_policy_id"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN ai_policy_id INTEGER NULL"
                )
            )

        if not await _column_exists(conn, "inspection_configs", "alert_ai_model_id"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN alert_ai_model_id INTEGER NULL"
                )
            )

        if not await _column_exists(conn, "inspection_configs", "ai_shadow_enabled"):
            await conn.execute(
                text(
                    "ALTER TABLE inspection_configs "
                    "ADD COLUMN ai_shadow_enabled BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )

        if await _column_exists(conn, "alert_ai_evaluation_logs", "id"):
            if not await _column_exists(conn, "alert_ai_evaluation_logs", "policy_severity_hint"):
                await conn.execute(
                    text(
                        "ALTER TABLE alert_ai_evaluation_logs "
                        "ADD COLUMN policy_severity_hint VARCHAR(20) NULL"
                    )
                )
            if not await _column_exists(conn, "alert_ai_evaluation_logs", "severity_source"):
                await conn.execute(
                    text(
                        "ALTER TABLE alert_ai_evaluation_logs "
                        "ADD COLUMN severity_source VARCHAR(20) NULL"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_alert_ai_evaluation_logs_severity_source "
                        "ON alert_ai_evaluation_logs (severity_source)"
                    )
                )

        logger.info("Migration complete: inspection_configs extended for alert AI engine")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
