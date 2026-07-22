"""Add the persisted UI locale to app_user."""

import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE app_user
            ADD COLUMN IF NOT EXISTS locale VARCHAR(10)
        """))
        await conn.execute(text("""
            UPDATE app_user SET locale = 'zh-CN'
            WHERE locale IS NULL OR locale NOT IN ('zh-CN', 'en-US')
        """))
        await conn.execute(text("""
            ALTER TABLE app_user ALTER COLUMN locale SET DEFAULT 'zh-CN'
        """))
        await conn.execute(text("""
            ALTER TABLE app_user ALTER COLUMN locale SET NOT NULL
        """))
    logger.info("Ensured app_user.locale exists and is populated")


async def downgrade():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE app_user DROP COLUMN IF EXISTS locale"))
