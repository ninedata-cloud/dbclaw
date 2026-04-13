import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


DEPRECATED_COLUMNS = [
    "ai_analysis",
    "knowledge_sources",
    "is_scheduled",
    "schedule_config_id",
    "retention_days",
]


async def _column_exists(conn, column_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'reports'
                  AND column_name = :column_name
            )
            """
        ),
        {"column_name": column_name},
    )
    return bool(result.scalar_one())


async def migrate():
    async with get_engine().begin() as conn:
        existing = [column for column in DEPRECATED_COLUMNS if await _column_exists(conn, column)]
        if not existing:
            logger.info("No deprecated report columns to archive/drop")
            return

        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS archive"))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS archive.report_deprecated_fields (
                    source_schema VARCHAR(255) NOT NULL,
                    report_id INTEGER NOT NULL,
                    ai_analysis TEXT NULL,
                    knowledge_sources JSONB NULL,
                    is_scheduled BOOLEAN NULL,
                    schedule_config_id INTEGER NULL,
                    retention_days INTEGER NULL,
                    archived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_schema, report_id)
                )
                """
            )
        )

        insert_columns = ["source_schema", "report_id", *existing]
        select_columns = ["current_schema()", "id"]
        update_assignments = []

        for column in existing:
            if column == "knowledge_sources":
                select_columns.append(
                    "CASE WHEN knowledge_sources IS NULL THEN NULL ELSE CAST(knowledge_sources AS JSONB) END"
                )
            else:
                select_columns.append(column)
            update_assignments.append(f"{column} = EXCLUDED.{column}")

        sql = f"""
            INSERT INTO archive.report_deprecated_fields ({", ".join(insert_columns)})
            SELECT {", ".join(select_columns)}
            FROM reports
            ON CONFLICT (source_schema, report_id) DO UPDATE
            SET
                {", ".join(update_assignments)},
                archived_at = CURRENT_TIMESTAMP
        """
        await conn.execute(text(sql))

        for column in existing:
            logger.info("Dropping reports.%s", column)
            await conn.execute(text(f"ALTER TABLE reports DROP COLUMN {column}"))

    logger.info("Deprecated report columns archived and dropped")
