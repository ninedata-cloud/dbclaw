"""
添加 SSH Agent 认证支持

运行方式：
    python backend/migrations/add_ssh_agent_auth.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import async_engine


async def migrate():
    """执行迁移"""
    async with async_engine.begin() as conn:
        print("检查 hosts 表的 auth_type 字段...")

        # 检查是否需要更新字段长度（从 VARCHAR(20) 确保足够存储 'agent'）
        # PostgreSQL 中 VARCHAR(20) 已经足够，但我们可以添加注释说明支持的值

        result = await conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'hosts' AND column_name = 'auth_type'
        """))

        row = result.fetchone()
        if row:
            print(f"当前 auth_type 字段: {row[1]}({row[2]})")
            print("✓ auth_type 字段已存在，支持 'agent' 值")
        else:
            print("✗ auth_type 字段不存在")
            return

        # 添加表注释说明支持的认证类型
        await conn.execute(text("""
            COMMENT ON COLUMN hosts.auth_type IS 'Authentication type: password, key, or agent'
        """))

        print("✓ 迁移完成")
        print("\n支持的认证类型：")
        print("  - password: 密码认证")
        print("  - key: 私钥认证")
        print("  - agent: SSH Agent 认证（新增）")


if __name__ == "__main__":
    asyncio.run(migrate())
