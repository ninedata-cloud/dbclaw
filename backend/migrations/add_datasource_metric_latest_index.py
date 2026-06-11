"""Add an index for per-datasource latest metric lookups."""
import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_datasource_metric_latest_lookup
            ON datasource_metric (datasource_id, metric_type, collected_at DESC, id DESC)
        """))
        logger.info("Ensured idx_datasource_metric_latest_lookup index")


async def downgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text("""
            DROP INDEX IF EXISTS idx_datasource_metric_latest_lookup
        """))
        logger.info("Dropped idx_datasource_metric_latest_lookup index")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
