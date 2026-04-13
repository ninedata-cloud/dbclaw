import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def _table_exists(conn, schema_name: str, table_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema_name AND table_name = :table_name
            )
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return bool(result.scalar_one())


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar_one())


async def migrate():
    async with get_engine().begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS archive"))

        if await _table_exists(conn, "public", "adapter_configs") and not await _table_exists(conn, "archive", "adapter_configs"):
            logger.info("Archiving public.adapter_configs into archive schema")
            await conn.execute(text("ALTER TABLE public.adapter_configs SET SCHEMA archive"))

        if await _table_exists(conn, "public", "adapter_execution_logs") and not await _table_exists(conn, "archive", "adapter_execution_logs"):
            logger.info("Archiving public.adapter_execution_logs into archive schema")
            await conn.execute(text("ALTER TABLE public.adapter_execution_logs SET SCHEMA archive"))

        if await _column_exists(conn, "datasources", "adapter_id"):
            logger.info("Archiving datasources.adapter_id values")
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS archive.datasource_adapter_mapping (
                        datasource_id INTEGER PRIMARY KEY,
                        adapter_id VARCHAR(100) NOT NULL,
                        archived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO archive.datasource_adapter_mapping (datasource_id, adapter_id)
                    SELECT id, adapter_id
                    FROM public.datasources
                    WHERE adapter_id IS NOT NULL
                    ON CONFLICT (datasource_id)
                    DO UPDATE SET
                        adapter_id = EXCLUDED.adapter_id,
                        archived_at = CURRENT_TIMESTAMP
                    """
                )
            )
            await conn.execute(text("ALTER TABLE public.datasources DROP COLUMN adapter_id"))

    logger.info("Legacy adapter schema archived and removed from public schema")

