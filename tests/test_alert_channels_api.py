#!/usr/bin/env python3
"""
测试 Alert Channels API
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.user import User
from backend.routers.integration import list_channels
from backend.database import get_db
from sqlalchemy import select


async def test_api():
    """测试 API"""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 获取用户
        result = await db.execute(select(User).where(User.id == 1))
        user = result.scalar_one_or_none()

        if not user:
            print("✗ 用户不存在")
            return

        print(f"✓ 用户: {user.username}")

        # 调用 API
        try:
            channels = await list_channels(
                integration_id=None,
                enabled=None,
                db=db,
                current_user=user
            )

            print(f"\n✓ API 调用成功")
            print(f"  - 返回 {len(channels)} 个通道")

            for channel in channels:
                print(f"\n通道 {channel.id}:")
                print(f"  - 名称: {channel.name}")
                print(f"  - Integration ID: {channel.integration_id}")
                print(f"  - Integration Name: {channel.integration_name}")
                print(f"  - Enabled: {channel.enabled}")

        except Exception as e:
            print(f"\n✗ API 调用失败: {e}")
            import traceback
            traceback.print_exc()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_api())
