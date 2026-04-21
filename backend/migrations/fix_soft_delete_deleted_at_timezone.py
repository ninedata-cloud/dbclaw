"""
Fix soft-delete deleted_at columns to TIMESTAMP WITH TIME ZONE.
将软删除 deleted_at 列统一修复为带时区时间类型。
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)

TABLES = (
    "datasource",
    "user",
    "host",
    "doc_document",
    "integration",
    "alert_subscription",
    "diagnostic_session",
    "chat_message",
    "report",
)


async def migrate(max_retries: int = 3) -> None:
    for attempt in range(1, max_retries + 1):
        async with async_session() as db:
            try:
                changed = 0
                skipped = 0
                for table_name in TABLES:
                    info = await db.execute(
                        text(
                            """
                            SELECT data_type
                            FROM information_schema.columns
                            WHERE table_schema = current_schema()
                              AND table_name = :table_name
                              AND column_name = 'deleted_at'
                            """
                        ),
                        {"table_name": table_name},
                    )
                    data_type = info.scalar_one_or_none()
                    if data_type is None:
                        skipped += 1
                        continue
                    if data_type == "timestamp with time zone":
                        skipped += 1
                        continue
                    if data_type != "timestamp without time zone":
                        logger.warning(
                            "Skip %s.deleted_at: unexpected type %s",
                            table_name,
                            data_type,
                        )
                        skipped += 1
                        continue

                    await db.execute(
                        text(
                            f"""
                            ALTER TABLE "{table_name}"
                            ALTER COLUMN "deleted_at"
                            TYPE TIMESTAMP WITH TIME ZONE
                            USING "deleted_at" AT TIME ZONE 'UTC'
                            """
                        )
                    )
                    changed += 1

                await db.commit()
                logger.info(
                    "Soft-delete deleted_at timezone migration completed: changed=%s skipped=%s",
                    changed,
                    skipped,
                )
                return
            except Exception as exc:
                await db.rollback()
                if "deadlock detected" in str(exc).lower() and attempt < max_retries:
                    logger.warning(
                        "deleted_at timezone migration deadlocked on attempt %s/%s, retrying",
                        attempt,
                        max_retries,
                    )
                    await asyncio.sleep(1)
                    continue
                raise


if __name__ == "__main__":
    asyncio.run(migrate())
