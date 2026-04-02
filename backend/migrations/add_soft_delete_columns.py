"""
Add soft delete columns to core business tables
为核心业务表增加逻辑删除字段

Usage:
    python backend/migrations/add_soft_delete_columns.py
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


TABLES = [
    "datasources",
    "users",
    "hosts",
    "doc_documents",
    "integrations",
    "alert_subscriptions",
    "diagnostic_sessions",
    "chat_messages",
    "reports",
]


async def _column_exists(db, table_name: str, column_name: str) -> bool:
    result = await db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = :table_name AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name})
    return result.first() is not None


async def _index_exists(db, index_name: str) -> bool:
    result = await db.execute(text("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = current_schema() AND indexname = :index_name
    """), {"index_name": index_name})
    return result.first() is not None


async def migrate(max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        async with async_session() as db:
            try:
                for table_name in TABLES:
                    if not await _column_exists(db, table_name, "is_deleted"):
                        await db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE"))
                        print(f"✓ {table_name}: added is_deleted")
                    else:
                        print(f"- {table_name}: is_deleted already exists")

                    if not await _column_exists(db, table_name, "deleted_at"):
                        await db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN deleted_at TIMESTAMP NULL"))
                        print(f"✓ {table_name}: added deleted_at")
                    else:
                        print(f"- {table_name}: deleted_at already exists")

                    if not await _column_exists(db, table_name, "deleted_by"):
                        await db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN deleted_by INTEGER NULL"))
                        print(f"✓ {table_name}: added deleted_by")
                    else:
                        print(f"- {table_name}: deleted_by already exists")

                    index_name = f"idx_{table_name}_is_deleted"
                    if not await _index_exists(db, index_name):
                        await db.execute(text(f"CREATE INDEX {index_name} ON {table_name}(is_deleted)"))
                        print(f"✓ {table_name}: created {index_name}")
                    else:
                        print(f"- {table_name}: {index_name} already exists")

                await db.commit()
                print("\n✓ Soft delete migration completed successfully")
                return
            except Exception as e:
                await db.rollback()
                if "deadlock detected" in str(e).lower() and attempt < max_retries:
                    logger.warning("Soft delete migration deadlocked on attempt %s/%s, retrying", attempt, max_retries)
                    await asyncio.sleep(1)
                    continue
                print(f"\n✗ Migration failed: {e}")
                raise


if __name__ == "__main__":
    asyncio.run(migrate())
