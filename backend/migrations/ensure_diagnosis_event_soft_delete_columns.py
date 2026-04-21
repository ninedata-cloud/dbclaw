import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        for column_name, ddl in (
            (
                "is_deleted",
                'ALTER TABLE "diagnosis_event" ADD COLUMN "is_deleted" BOOLEAN NOT NULL DEFAULT FALSE',
            ),
            (
                "deleted_at",
                'ALTER TABLE "diagnosis_event" ADD COLUMN "deleted_at" TIMESTAMP WITH TIME ZONE',
            ),
            (
                "deleted_by",
                'ALTER TABLE "diagnosis_event" ADD COLUMN "deleted_by" INTEGER',
            ),
        ):
            exists_result = await conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'diagnosis_event'
                      AND column_name = :column_name
                    """
                ),
                {"column_name": column_name},
            )
            if exists_result.first() is None:
                await conn.execute(text(ddl))

    logger.info("diagnosis_event soft-delete columns ensured")
