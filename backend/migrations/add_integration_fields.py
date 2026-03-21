"""
添加 Integration 系统所需的新字段

执行时间：2026-03-18
"""

import asyncio
from sqlalchemy import text
from backend.database import async_session


async def migrate():
    """执行迁移"""
    async with async_session() as db:
        print("开始迁移：添加 Integration 字段...")

        # 添加 integration_id 字段
        print("1. 添加 integration_id 字段到 integrations 表...")
        await db.execute(text("""
            ALTER TABLE integrations
            ADD COLUMN IF NOT EXISTS integration_id VARCHAR(100) UNIQUE
        """))

        # 为现有记录生成 integration_id
        print("2. 为现有记录生成 integration_id...")
        await db.execute(text("""
            UPDATE integrations
            SET integration_id = 'custom_' || id
            WHERE integration_id IS NULL
        """))

        # 添加 config_schema 字段
        print("3. 添加 config_schema 字段到 integrations 表...")
        await db.execute(text("""
            ALTER TABLE integrations
            ADD COLUMN IF NOT EXISTS config_schema JSONB
        """))

        # 添加 channel_ids 字段到 alert_subscriptions
        print("4. 添加 channel_ids 字段到 alert_subscriptions 表...")
        await db.execute(text("""
            ALTER TABLE alert_subscriptions
            ADD COLUMN IF NOT EXISTS channel_ids JSONB DEFAULT '[]'
        """))

        # 添加 user_id 字段到 alert_channels（用于权限控制）
        print("5. 添加 user_id 字段到 alert_channels 表...")
        await db.execute(text("""
            ALTER TABLE alert_channels
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        """))

        # 删除旧的 config 字段（如果存在）
        print("6. 删除 integrations 表的旧 config 字段...")
        await db.execute(text("""
            ALTER TABLE integrations
            DROP COLUMN IF EXISTS config
        """))

        await db.commit()
        print("迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
