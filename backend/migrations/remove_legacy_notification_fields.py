#!/usr/bin/env python3
"""
移除告警订阅表中的旧通知字段
将所有通知切换到 Integration 系统
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from backend.config import settings


async def migrate():
    """移除旧的通知字段"""
    engine = create_async_engine(settings.database_url, echo=True)

    async with engine.begin() as conn:
        print("开始迁移：移除旧的通知字段...")

        # 检查字段是否存在
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'alert_subscriptions'
            AND column_name IN ('channels', 'webhook_url', 'dingtalk_webhook_url', 'dingtalk_secret')
        """))
        existing_columns = [row[0] for row in result.fetchall()]

        if not existing_columns:
            print("✓ 旧字段已经被移除，无需迁移")
            return

        print(f"发现旧字段: {', '.join(existing_columns)}")

        # 移除旧字段
        for column in existing_columns:
            try:
                await conn.execute(text(f"""
                    ALTER TABLE alert_subscriptions DROP COLUMN IF EXISTS {column}
                """))
                print(f"✓ 已移除字段: {column}")
            except Exception as e:
                print(f"✗ 移除字段 {column} 失败: {e}")

        print("✓ 迁移完成")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
