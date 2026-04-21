"""
Normalize skill-related table column types and defaults.
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


async def _table_exists(db, table_name: str) -> bool:
    result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar_one())


async def _column_type(db, table_name: str, column_name: str) -> str | None:
    result = await db.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none()


async def migrate() -> None:
    async with async_session() as db:
        if await _table_exists(db, "skill"):
            await db.execute(text("UPDATE skill SET tags = '[]'::json WHERE tags IS NULL"))
            await db.execute(text("UPDATE skill SET parameters = '[]'::json WHERE parameters IS NULL"))
            await db.execute(text("UPDATE skill SET dependencies = '[]'::json WHERE dependencies IS NULL"))
            await db.execute(text("UPDATE skill SET permissions = '[]'::json WHERE permissions IS NULL"))
            await db.execute(text("UPDATE skill SET is_builtin = FALSE WHERE is_builtin IS NULL"))
            await db.execute(text("UPDATE skill SET is_enabled = TRUE WHERE is_enabled IS NULL"))

            await db.execute(
                text(
                    """
                    ALTER TABLE skill
                    ALTER COLUMN tags SET DEFAULT '[]'::json,
                    ALTER COLUMN tags SET NOT NULL,
                    ALTER COLUMN parameters SET DEFAULT '[]'::json,
                    ALTER COLUMN parameters SET NOT NULL,
                    ALTER COLUMN dependencies SET DEFAULT '[]'::json,
                    ALTER COLUMN dependencies SET NOT NULL,
                    ALTER COLUMN permissions SET DEFAULT '[]'::json,
                    ALTER COLUMN permissions SET NOT NULL,
                    ALTER COLUMN is_builtin SET DEFAULT FALSE,
                    ALTER COLUMN is_builtin SET NOT NULL,
                    ALTER COLUMN is_enabled SET DEFAULT TRUE,
                    ALTER COLUMN is_enabled SET NOT NULL,
                    ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
                    ALTER COLUMN created_at SET NOT NULL,
                    ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC',
                    ALTER COLUMN updated_at SET NOT NULL
                    """
                )
            )

        if await _table_exists(db, "skill_execution"):
            col_type = await _column_type(db, "skill_execution", "id")
            if col_type == "integer":
                await db.execute(text("ALTER TABLE skill_execution ALTER COLUMN id TYPE BIGINT"))

            await db.execute(
                text(
                    """
                    ALTER TABLE skill_execution
                    ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
                    ALTER COLUMN created_at SET NOT NULL
                    """
                )
            )

        if await _table_exists(db, "skill_rating"):
            col_type = await _column_type(db, "skill_rating", "id")
            if col_type == "integer":
                await db.execute(text("ALTER TABLE skill_rating ALTER COLUMN id TYPE BIGINT"))

            await db.execute(
                text(
                    """
                    ALTER TABLE skill_rating
                    ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
                    ALTER COLUMN created_at SET NOT NULL
                    """
                )
            )

        await db.commit()
        logger.info("Skill model columns normalized")


if __name__ == "__main__":
    asyncio.run(migrate())
