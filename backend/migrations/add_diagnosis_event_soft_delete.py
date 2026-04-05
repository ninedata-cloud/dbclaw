import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        for column_def in [
            ("is_deleted", "ALTER TABLE diagnosis_events ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE"),
            ("deleted_at", "ALTER TABLE diagnosis_events ADD COLUMN deleted_at TIMESTAMP"),
            ("deleted_by", "ALTER TABLE diagnosis_events ADD COLUMN deleted_by INTEGER"),
        ]:
            column_name, ddl = column_def
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='diagnosis_events' AND column_name=:column_name"
            ), {"column_name": column_name})
            if not result.scalar_one_or_none():
                await conn.execute(text(ddl))

    logger.info("diagnosis_events soft-delete columns ready")
