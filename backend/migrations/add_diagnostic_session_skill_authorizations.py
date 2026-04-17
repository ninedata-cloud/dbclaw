"""Add skill_authorizations column to diagnostic_sessions."""
import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name='diagnostic_sessions' AND column_name='skill_authorizations'"
                ")"
            )
        )
        if not result.scalar_one():
            await conn.execute(
                text("ALTER TABLE diagnostic_sessions ADD COLUMN skill_authorizations JSON NULL")
            )
            logger.info("Added skill_authorizations column to diagnostic_sessions")

    logger.info("Migration complete: diagnostic_sessions.skill_authorizations")


if __name__ == "__main__":
    asyncio.run(migrate())
