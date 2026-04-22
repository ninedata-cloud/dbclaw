"""添加 inspection_trigger.error_message 字段

迁移说明：
- 添加 error_message 字段到 inspection_trigger 表
- 用于记录报告生成失败时的错误信息
"""
import logging
from sqlalchemy import text
from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    """添加 error_message 字段"""
    engine = get_engine()

    async with engine.begin() as conn:
        # 检查字段是否已存在
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'inspection_trigger'
            AND column_name = 'error_message'
        """))

        if result.fetchone() is None:
            # 字段不存在，添加它
            await conn.execute(text("""
                ALTER TABLE inspection_trigger
                ADD COLUMN error_message TEXT
            """))
            logger.info("Added error_message column to inspection_trigger table")
        else:
            logger.info("error_message column already exists in inspection_trigger table")


async def downgrade():
    """移除 error_message 字段"""
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE inspection_trigger
            DROP COLUMN IF EXISTS error_message
        """))
        logger.info("Removed error_message column from inspection_trigger table")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
