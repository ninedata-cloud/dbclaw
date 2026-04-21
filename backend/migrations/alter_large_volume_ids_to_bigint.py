"""
将高增长表主键及直接关联列从 integer 升级为 bigint。
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


TARGET_COLUMNS: dict[str, tuple[str, ...]] = {
    "alert_message": ("id",),
    "chat_message": ("id",),
    "diagnosis_event": ("id",),
    "alert_event": ("first_alert_id", "latest_alert_id"),
    "alert_ai_runtime_state": ("alert_id",),
    "alert_delivery_log": ("alert_id",),
    "inspection_trigger": ("alert_id",),
    "report": ("alert_id",),
}


async def _get_column_type(db, table_name: str, column_name: str) -> str | None:
    result = await db.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none()


async def migrate() -> None:
    async with async_session() as db:
        changed = 0
        skipped = 0
        for table_name, columns in TARGET_COLUMNS.items():
            for column_name in columns:
                data_type = await _get_column_type(db, table_name, column_name)
                if data_type is None:
                    skipped += 1
                    continue
                if data_type == "bigint":
                    skipped += 1
                    continue
                if data_type != "integer":
                    logger.warning(
                        "Skip %s.%s: unexpected type %s",
                        table_name,
                        column_name,
                        data_type,
                    )
                    skipped += 1
                    continue

                await db.execute(
                    text(
                        f"""
                        ALTER TABLE "{table_name}"
                        ALTER COLUMN "{column_name}" TYPE BIGINT
                        """
                    )
                )
                changed += 1

        await db.commit()
        logger.info("Large-volume bigint migration completed: changed=%s skipped=%s", changed, skipped)


if __name__ == "__main__":
    asyncio.run(migrate())
