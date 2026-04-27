"""添加 ai_model.reasoning_effort 字段

迁移说明：
- 在 ai_model 表新增 reasoning_effort 列
- 用于配置推理强度（low/medium/high）
"""
import logging
from sqlalchemy import text
from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    """添加 reasoning_effort 字段"""
    engine = get_engine()

    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'ai_model'
            AND column_name = 'reasoning_effort'
        """))

        if result.fetchone() is None:
            await conn.execute(text("""
                ALTER TABLE ai_model
                ADD COLUMN reasoning_effort VARCHAR
            """))
            logger.info("Added reasoning_effort column to ai_model table")
        else:
            logger.info("reasoning_effort column already exists in ai_model table")


async def downgrade():
    """移除 reasoning_effort 字段"""
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE ai_model
            DROP COLUMN IF EXISTS reasoning_effort
        """))
        logger.info("Removed reasoning_effort column from ai_model table")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
