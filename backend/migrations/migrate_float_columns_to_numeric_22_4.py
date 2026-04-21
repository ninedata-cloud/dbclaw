"""
将历史浮点/数值列统一迁移为 NUMERIC(22,4)。
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


TARGET_COLUMNS: dict[str, tuple[str, ...]] = {
    "alert_message": ("metric_value", "threshold_value", "resolved_value"),
    "host_metric": ("cpu_usage", "memory_usage", "disk_usage"),
    "metric_baseline_profile": (
        "avg_value",
        "min_value",
        "max_value",
        "p50_value",
        "p95_value",
        "stddev_value",
    ),
    "alert_ai_evaluation_log": ("confidence",),
    "alert_ai_runtime_state": ("last_confidence",),
    "diagnosis_conclusion": ("confidence",),
}


async def migrate() -> None:
    async with async_session() as db:
        changed = 0
        skipped = 0

        for table_name, column_names in TARGET_COLUMNS.items():
            for column_name in column_names:
                info = await db.execute(
                    text(
                        """
                        SELECT data_type, numeric_precision, numeric_scale
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = :table_name
                          AND column_name = :column_name
                        """
                    ),
                    {"table_name": table_name, "column_name": column_name},
                )
                row = info.one_or_none()
                if row is None:
                    skipped += 1
                    continue

                data_type, numeric_precision, numeric_scale = row
                if (
                    data_type == "numeric"
                    and numeric_precision == 22
                    and numeric_scale == 4
                ):
                    skipped += 1
                    continue

                await db.execute(
                    text(
                        f"""
                        ALTER TABLE "{table_name}"
                        ALTER COLUMN "{column_name}"
                        TYPE NUMERIC(22,4)
                        USING ROUND("{column_name}"::numeric, 4)
                        """
                    )
                )
                changed += 1

        await db.commit()
        logger.info(
            "Numeric precision migration completed: changed=%s skipped=%s",
            changed,
            skipped,
        )


if __name__ == "__main__":
    asyncio.run(migrate())
