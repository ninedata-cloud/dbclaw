# backend/migrations/replace_knowledge_base_with_documents.py
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    """删除旧知识库表（如存在），新表由 SQLAlchemy create_all 自动创建"""
    async with async_session() as db:
        for table in ["knowledge_chunks", "documents", "knowledge_bases"]:
            try:
                await db.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                logger.info(f"Dropped table: {table}")
            except Exception as e:
                logger.warning(f"Could not drop {table}: {e}")
        await db.commit()
