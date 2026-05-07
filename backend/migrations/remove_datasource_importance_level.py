"""移除 datasource.importance_level 字段。"""
import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE datasource
            DROP COLUMN IF EXISTS importance_level
        """))
        logger.info("Removed importance_level column from datasource table")


async def downgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE datasource
            ADD COLUMN IF NOT EXISTS importance_level VARCHAR(20) DEFAULT 'production'
        """))
        logger.info("Restored importance_level column on datasource table")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
