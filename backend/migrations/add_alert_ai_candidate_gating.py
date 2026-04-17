"""
Migration: extend alert AI policy/runtime tables for candidate gating.
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
        policy_columns = [
            ("analysis_strategy", "ALTER TABLE alert_ai_policies ADD COLUMN analysis_strategy VARCHAR(32) NOT NULL DEFAULT 'candidate_only'"),
            ("analysis_config", "ALTER TABLE alert_ai_policies ADD COLUMN analysis_config JSONB NOT NULL DEFAULT '{}'::jsonb"),
            ("compiled_trigger_profile", "ALTER TABLE alert_ai_policies ADD COLUMN compiled_trigger_profile JSONB NULL"),
            ("compile_status", "ALTER TABLE alert_ai_policies ADD COLUMN compile_status VARCHAR(20) NOT NULL DEFAULT 'pending'"),
            ("compile_error", "ALTER TABLE alert_ai_policies ADD COLUMN compile_error TEXT NULL"),
            ("compiled_at", "ALTER TABLE alert_ai_policies ADD COLUMN compiled_at TIMESTAMP NULL"),
        ]
        for column_name, ddl in policy_columns:
            if not await _column_exists(conn, "alert_ai_policies", column_name):
                await conn.execute(text(ddl))

        runtime_columns = [
            ("last_candidate_type", "ALTER TABLE alert_ai_runtime_states ADD COLUMN last_candidate_type VARCHAR(32) NULL"),
            ("last_candidate_fingerprint", "ALTER TABLE alert_ai_runtime_states ADD COLUMN last_candidate_fingerprint VARCHAR(128) NULL"),
            ("last_ai_evaluated_at", "ALTER TABLE alert_ai_runtime_states ADD COLUMN last_ai_evaluated_at TIMESTAMP NULL"),
            ("last_gate_reason", "ALTER TABLE alert_ai_runtime_states ADD COLUMN last_gate_reason VARCHAR(64) NULL"),
            ("last_gate_metrics", "ALTER TABLE alert_ai_runtime_states ADD COLUMN last_gate_metrics JSONB NULL"),
            ("samples_seen", "ALTER TABLE alert_ai_runtime_states ADD COLUMN samples_seen INTEGER NOT NULL DEFAULT 0"),
            ("candidate_hits", "ALTER TABLE alert_ai_runtime_states ADD COLUMN candidate_hits INTEGER NOT NULL DEFAULT 0"),
            ("ai_evaluations", "ALTER TABLE alert_ai_runtime_states ADD COLUMN ai_evaluations INTEGER NOT NULL DEFAULT 0"),
            ("gate_skips_by_reason", "ALTER TABLE alert_ai_runtime_states ADD COLUMN gate_skips_by_reason JSONB NULL"),
        ]
        for column_name, ddl in runtime_columns:
            if not await _column_exists(conn, "alert_ai_runtime_states", column_name):
                await conn.execute(text(ddl))

        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_ai_policies_compile_status "
                "ON alert_ai_policies (compile_status)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_ai_runtime_states_last_candidate_type "
                "ON alert_ai_runtime_states (last_candidate_type)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_alert_ai_runtime_states_last_ai_evaluated_at "
                "ON alert_ai_runtime_states (last_ai_evaluated_at)"
            )
        )

        logger.info("Migration complete: alert AI policy/runtime candidate gating columns added")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
