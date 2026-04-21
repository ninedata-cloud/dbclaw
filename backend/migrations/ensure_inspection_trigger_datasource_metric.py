"""
Ensure inspection_trigger.datasource_metric exists and uses JSON.
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate() -> None:
    async with async_session() as db:
        table_exists = await db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = 'inspection_trigger'
                )
                """
            )
        )
        if not table_exists.scalar_one():
            logger.info("Skip migration: inspection_trigger table does not exist")
            return

        column_info = await db.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspection_trigger'
                  AND column_name = 'datasource_metric'
                """
            )
        )
        data_type = column_info.scalar_one_or_none()

        if data_type is None:
            await db.execute(
                text(
                    """
                    ALTER TABLE inspection_trigger
                    ADD COLUMN datasource_metric JSON NULL
                    """
                )
            )
            await db.commit()
            logger.info("Added missing column inspection_trigger.datasource_metric (JSON)")
            return

        if data_type == "json":
            logger.info("inspection_trigger.datasource_metric already JSON")
            return

        if data_type == "jsonb":
            await db.execute(
                text(
                    """
                    ALTER TABLE inspection_trigger
                    ALTER COLUMN datasource_metric
                    TYPE JSON
                    USING datasource_metric::json
                    """
                )
            )
            await db.commit()
            logger.info("Converted inspection_trigger.datasource_metric from JSONB to JSON")
            return

        if data_type in {"text", "character varying"}:
            await db.execute(
                text(
                    """
                    ALTER TABLE inspection_trigger
                    ALTER COLUMN datasource_metric
                    TYPE JSON
                    USING CASE
                        WHEN datasource_metric IS NULL THEN NULL
                        ELSE to_json(datasource_metric)
                    END
                    """
                )
            )
            await db.commit()
            logger.info(
                "Converted inspection_trigger.datasource_metric from %s to JSON",
                data_type,
            )
            return

        logger.warning(
            "Skip migration: unexpected inspection_trigger.datasource_metric type=%s",
            data_type,
        )


if __name__ == "__main__":
    asyncio.run(migrate())
