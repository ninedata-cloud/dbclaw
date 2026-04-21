"""
将业务表中的 JSONB 列统一转换为 JSON（PostgreSQL）。
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate() -> None:
    async with async_session() as db:
        columns = await db.execute(
            text(
                """
                SELECT table_name, column_name, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND udt_name = 'jsonb'
                ORDER BY table_name, column_name
                """
            )
        )

        changed = 0
        for table_name, column_name, column_default in columns.fetchall():
            await db.execute(
                text(
                    f"""
                    ALTER TABLE "{table_name}"
                    ALTER COLUMN "{column_name}"
                    TYPE JSON
                    USING "{column_name}"::json
                    """
                )
            )

            normalized_default = None
            if column_default:
                normalized_default = (
                    column_default.replace("::jsonb", "::json").replace("::JSONB", "::json")
                )

            if normalized_default and normalized_default != column_default:
                await db.execute(
                    text(
                        f"""
                        ALTER TABLE "{table_name}"
                        ALTER COLUMN "{column_name}"
                        SET DEFAULT {normalized_default}
                        """
                    )
                )

            changed += 1

        await db.commit()
        logger.info("JSONB to JSON migration completed: changed=%s", changed)


if __name__ == "__main__":
    asyncio.run(migrate())
