import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def _column_type(conn, column_name: str) -> str | None:
    result = await conn.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'ai_model'
              AND column_name = :column_name
            """
        ),
        {"column_name": column_name},
    )
    return result.scalar_one_or_none()


async def migrate():
    async with get_engine().begin() as conn:
        for column_name in ("created_at", "updated_at"):
            column_type = await _column_type(conn, column_name)
            if column_type != "timestamp with time zone":
                continue

            logger.info("Normalizing ai_model.%s to UTC naive timestamp", column_name)
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE ai_model
                    ALTER COLUMN {column_name} TYPE TIMESTAMP WITHOUT TIME ZONE
                    USING {column_name} AT TIME ZONE 'UTC'
                    """
                )
            )

    logger.info("ai_model timestamp columns normalized")
