"""
扩展 alert_delivery_log.channel 字段长度

执行: python backend/migrations/expand_alert_delivery_log_channel.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import engine


async def expand_channel_field():
    """扩展 channel 字段长度从 20 到 100"""

    async with engine.begin() as conn:
        print("正在扩展 alert_delivery_log.channel 字段长度...")

        # 修改字段类型
        await conn.execute(text(
            "ALTER TABLE alert_delivery_log ALTER COLUMN channel TYPE VARCHAR(100)"
        ))

        print("✓ 字段长度已扩展为 VARCHAR(100)")


if __name__ == "__main__":
    asyncio.run(expand_channel_field())
