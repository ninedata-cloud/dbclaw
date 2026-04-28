"""移除 scheduled_task 任务级参数配置字段。"""
import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE scheduled_task
            DROP COLUMN IF EXISTS params
        """))
        logger.info("Removed params column from scheduled_task table")


async def downgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE scheduled_task
            ADD COLUMN IF NOT EXISTS params JSONB
        """))
        logger.info("Restored params column on scheduled_task table")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
