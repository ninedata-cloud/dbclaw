"""
添加数据源监控来源配置字段

运行方式：
python backend/migrations/add_datasource_metric_source.py
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """添加 metric_source, adapter_id, external_instance_id 字段到 datasources 表"""
    async with engine.begin() as conn:
        logger.info("Starting migration: add datasource metric source fields")

        # 检查字段是否已存在
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'datasources'
            AND column_name IN ('metric_source', 'adapter_id', 'external_instance_id')
        """))
        existing_columns = {row[0] for row in result.fetchall()}

        # 添加 metric_source 字段
        if 'metric_source' not in existing_columns:
            logger.info("Adding column: metric_source")
            await conn.execute(text("""
                ALTER TABLE datasources
                ADD COLUMN metric_source VARCHAR(20) DEFAULT 'system' NOT NULL
            """))
            logger.info("✓ Added metric_source column")
        else:
            logger.info("Column metric_source already exists, skipping")

        # 添加 adapter_id 字段
        if 'adapter_id' not in existing_columns:
            logger.info("Adding column: adapter_id")
            await conn.execute(text("""
                ALTER TABLE datasources
                ADD COLUMN adapter_id VARCHAR(100)
            """))
            logger.info("✓ Added adapter_id column")
        else:
            logger.info("Column adapter_id already exists, skipping")

        # 添加 external_instance_id 字段
        if 'external_instance_id' not in existing_columns:
            logger.info("Adding column: external_instance_id")
            await conn.execute(text("""
                ALTER TABLE datasources
                ADD COLUMN external_instance_id VARCHAR(255)
            """))
            logger.info("✓ Added external_instance_id column")
        else:
            logger.info("Column external_instance_id already exists, skipping")

        logger.info("Migration completed successfully")


if __name__ == "__main__":
    asyncio.run(migrate())
