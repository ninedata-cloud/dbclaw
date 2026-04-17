"""
Migration: extend integration_execution_logs for direct target tracking.
"""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def _add_column_if_missing(conn, table_name: str, column_name: str, ddl: str):
    result = await conn.execute(text(
        "SELECT EXISTS ("
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        f"AND table_name = '{table_name}' AND column_name = '{column_name}'"
        ")"
    ))
    if result.scalar_one():
        return
    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


async def migrate():
    async with engine.begin() as conn:
        await _add_column_if_missing(conn, 'integration_execution_logs', 'target_type', 'target_type VARCHAR(50) NULL')
        await _add_column_if_missing(conn, 'integration_execution_logs', 'target_ref', 'target_ref VARCHAR(100) NULL')
        await _add_column_if_missing(conn, 'integration_execution_logs', 'subscription_id', 'subscription_id INTEGER NULL')
        await _add_column_if_missing(conn, 'integration_execution_logs', 'datasource_id', 'datasource_id INTEGER NULL')
        await _add_column_if_missing(conn, 'integration_execution_logs', 'target_name', 'target_name VARCHAR(255) NULL')
        await _add_column_if_missing(conn, 'integration_execution_logs', 'params_snapshot', "params_snapshot JSONB NULL")
        await _add_column_if_missing(conn, 'integration_execution_logs', 'payload_summary', "payload_summary JSONB NULL")
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_integration_execution_logs_target_type ON integration_execution_logs (target_type)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_integration_execution_logs_target_ref ON integration_execution_logs (target_ref)"))
        logger.info("Migration complete: extended integration_execution_logs")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
