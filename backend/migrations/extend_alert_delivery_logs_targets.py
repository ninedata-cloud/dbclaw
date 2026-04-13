"""
Migration: extend alert_delivery_logs with integration target metadata.
"""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def _add_column_if_missing(conn, table_name: str, column_name: str, ddl: str):
    result = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = current_schema() AND table_name = '{table_name}' AND column_name = '{column_name}'"
    ))
    if result.scalar_one_or_none():
        return
    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


async def migrate():
    async with engine.begin() as conn:
        await _add_column_if_missing(conn, 'alert_delivery_logs', 'integration_id', 'integration_id INTEGER NULL')
        await _add_column_if_missing(conn, 'alert_delivery_logs', 'target_id', 'target_id VARCHAR(100) NULL')
        await _add_column_if_missing(conn, 'alert_delivery_logs', 'target_name', 'target_name VARCHAR(255) NULL')
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alert_delivery_logs_integration_id ON alert_delivery_logs (integration_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alert_delivery_logs_target_id ON alert_delivery_logs (target_id)"))
        logger.info("Migration complete: extended alert_delivery_logs")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
