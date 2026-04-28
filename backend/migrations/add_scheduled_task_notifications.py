"""添加 scheduled_task 运行结果通知配置字段。"""
import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def _column_exists(conn, column_name: str) -> bool:
    result = await conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'scheduled_task'
        AND column_name = :column_name
    """), {"column_name": column_name})
    return result.fetchone() is not None


async def upgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        if not await _column_exists(conn, "notification_policy"):
            await conn.execute(text("""
                ALTER TABLE scheduled_task
                ADD COLUMN notification_policy VARCHAR(20) NOT NULL DEFAULT 'never'
            """))
            logger.info("Added notification_policy column to scheduled_task table")

        if not await _column_exists(conn, "notification_targets"):
            await conn.execute(text("""
                ALTER TABLE scheduled_task
                ADD COLUMN notification_targets JSONB NOT NULL DEFAULT '[]'::jsonb
            """))
            logger.info("Added notification_targets column to scheduled_task table")


async def downgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE scheduled_task
            DROP COLUMN IF EXISTS notification_targets,
            DROP COLUMN IF EXISTS notification_policy
        """))
        logger.info("Removed scheduled_task notification columns")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
