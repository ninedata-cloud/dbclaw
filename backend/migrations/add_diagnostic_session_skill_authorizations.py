"""Add skill_authorizations column to diagnostic_sessions."""
import asyncio

from sqlalchemy import text

from backend.database import engine


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='diagnostic_sessions' AND column_name='skill_authorizations'"
            )
        )
        if not result.scalar_one_or_none():
            await conn.execute(
                text("ALTER TABLE diagnostic_sessions ADD COLUMN skill_authorizations JSON NULL")
            )
            print("Added skill_authorizations column to diagnostic_sessions")

    print("Migration complete: diagnostic_sessions.skill_authorizations")


if __name__ == "__main__":
    asyncio.run(migrate())
