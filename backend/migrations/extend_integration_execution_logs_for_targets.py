"""
Migration: extend integration_execution_log for direct target tracking.
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
        await _add_column_if_missing(conn, 'integration_execution_log', 'target_type', 'target_type VARCHAR(50) NULL')
        await _add_column_if_missing(conn, 'integration_execution_log', 'target_ref', 'target_ref VARCHAR(100) NULL')
        await _add_column_if_missing(conn, 'integration_execution_log', 'subscription_id', 'subscription_id INTEGER NULL')
        await _add_column_if_missing(conn, 'integration_execution_log', 'datasource_id', 'datasource_id INTEGER NULL')
        await _add_column_if_missing(conn, 'integration_execution_log', 'target_name', 'target_name VARCHAR(255) NULL')
        await _add_column_if_missing(conn, 'integration_execution_log', 'params_snapshot', "params_snapshot JSON NULL")
        await _add_column_if_missing(conn, 'integration_execution_log', 'payload_summary', "payload_summary JSON NULL")
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_integration_execution_log_target_type ON integration_execution_log (target_type)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_integration_execution_log_target_ref ON integration_execution_log (target_ref)"))
        logger.info("Migration complete: extended integration_execution_log")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
