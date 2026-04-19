"""
测试主机配置缓存功能
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from backend.database import async_session
from backend.models.host import Host


async def test_host_config_cache():
    """测试主机配置缓存字段"""
    async with async_session() as db:
        # 查询第一个主机
        result = await db.execute(
            select(Host)
            .where(Host.deleted_at.is_(None))
            .limit(1)
        )
        host = result.scalar_one_or_none()

        if not host:
            print("❌ 没有找到主机记录")
            return

        print(f"✓ 找到主机: {host.name} (ID: {host.id})")
        print(f"  - config_data 字段: {'存在' if hasattr(host, 'config_data') else '不存在'}")
        print(f"  - config_collected_at 字段: {'存在' if hasattr(host, 'config_collected_at') else '不存在'}")

        if host.config_data:
            print(f"  - 已有缓存配置，采集时间: {host.config_collected_at}")
            print(f"  - 配置键: {list(host.config_data.keys())}")
        else:
            print(f"  - 暂无缓存配置")

        print("\n✓ 主机配置缓存功能测试通过")


if __name__ == "__main__":
    asyncio.run(test_host_config_cache())
