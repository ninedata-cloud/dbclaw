"""One-off migration: switch OceanBase MySQL-mode datasources to db_type='oceanbase_mysql'.

Rules (conservative):
- Only update rows currently marked as db_type='oceanbase'
- Only update rows using the MySQL compatible port 2881

Run:
  python backend/migrations/migrate_oceanbase_mysql_type.py

This project doesn't use Alembic; migrations are executed manually.
"""

import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    async with async_session() as db:
        # Dry count
        res = await db.execute(text(
            "SELECT count(*) FROM datasources WHERE db_type='oceanbase' AND port=2881"
        ))
        count = res.scalar_one() or 0
        logger.info("Found %s oceanbase rows on port 2881 to migrate", count)

        if count == 0:
            return

        await db.execute(text(
            "UPDATE datasources SET db_type='oceanbase_mysql' WHERE db_type='oceanbase' AND port=2881"
        ))
        await db.commit()
        logger.info("Migrated %s datasource(s) to oceanbase_mysql", count)


def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())


if __name__ == '__main__':
    main()
