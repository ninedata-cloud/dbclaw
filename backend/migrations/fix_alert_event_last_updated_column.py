"""
Fix legacy alert_event.last_updated column drift.

Some databases still carry a NOT NULL legacy `last_updated` column while
application code writes `updated_at`, causing inserts to fail.
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


async def _column_exists(db, column_name: str) -> bool:
    result = await db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'alert_event'
              AND column_name = :column_name
            """
        ),
        {"column_name": column_name},
    )
    return result.first() is not None


async def migrate(max_retries: int = 3) -> None:
    for attempt in range(1, max_retries + 1):
        async with async_session() as db:
            try:
                has_updated_at = await _column_exists(db, "updated_at")
                has_last_updated = await _column_exists(db, "last_updated")

                if has_last_updated and not has_updated_at:
                    await db.execute(
                        text(
                            """
                            ALTER TABLE "alert_event"
                            RENAME COLUMN "last_updated" TO "updated_at"
                            """
                        )
                    )
                    has_updated_at = True
                    has_last_updated = False

                if not has_updated_at:
                    await db.execute(
                        text(
                            """
                            ALTER TABLE "alert_event"
                            ADD COLUMN "updated_at" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                            """
                        )
                    )

                await db.execute(
                    text(
                        """
                        UPDATE "alert_event"
                        SET "updated_at" = COALESCE("updated_at", "created_at", CURRENT_TIMESTAMP)
                        WHERE "updated_at" IS NULL
                        """
                    )
                )
                await db.execute(
                    text(
                        """
                        ALTER TABLE "alert_event"
                        ALTER COLUMN "updated_at" SET DEFAULT CURRENT_TIMESTAMP,
                        ALTER COLUMN "updated_at" SET NOT NULL
                        """
                    )
                )

                if has_last_updated:
                    await db.execute(
                        text(
                            """
                            ALTER TABLE "alert_event"
                            DROP COLUMN "last_updated"
                            """
                        )
                    )

                await db.commit()
                logger.info("Alert_event timestamp column drift fixed")
                return
            except Exception as exc:
                await db.rollback()
                if "deadlock detected" in str(exc).lower() and attempt < max_retries:
                    logger.warning(
                        "alert_event last_updated migration deadlocked on attempt %s/%s, retrying",
                        attempt,
                        max_retries,
                    )
                    await asyncio.sleep(1)
                    continue
                raise


if __name__ == "__main__":
    asyncio.run(migrate())
