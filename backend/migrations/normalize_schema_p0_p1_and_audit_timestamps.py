"""
Normalize schema for P0/P1 and enforce audit timestamps.
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)

ALL_TABLES = (
    "ai_model",
    "alert_ai_evaluation_log",
    "alert_ai_policy",
    "alert_ai_runtime_state",
    "alert_delivery_log",
    "alert_event",
    "alert_message",
    "alert_subscription",
    "alert_template",
    "chat_channel_binding",
    "chat_event_dedup",
    "chat_message",
    "datasource",
    "datasource_metric",
    "diagnosis_conclusion",
    "diagnosis_event",
    "diagnostic_session",
    "doc_category",
    "doc_document",
    "host",
    "host_metric",
    "inspection_config",
    "inspection_trigger",
    "integration",
    "integration_bot_binding",
    "integration_execution_log",
    "login_log",
    "metric_baseline_profile",
    "report",
    "skill",
    "skill_execution",
    "skill_rating",
    "system_config",
    "user",
    "user_session",
)

RENAME_COLUMNS = (
    ("login_log", "login_time", "logged_in_at"),
    ("login_log", "success", "is_success"),
    ("inspection_trigger", "processed", "is_processed"),
    ("alert_template", "enabled", "is_enabled"),
    ("alert_subscription", "enabled", "is_enabled"),
    ("integration_bot_binding", "enabled", "is_enabled"),
    ("alert_ai_policy", "enabled", "is_enabled"),
    ("alert_ai_runtime_state", "active", "is_active"),
    ("alert_ai_evaluation_log", "trigger_inspection", "should_trigger_inspection"),
    ("alert_ai_evaluation_log", "accepted", "is_accepted"),
    ("inspection_config", "enabled", "is_enabled"),
    ("integration", "enabled", "is_enabled"),
    ("alert_event", "last_updated", "updated_at"),
    ("alert_event", "event_start_time", "event_started_at"),
    ("alert_event", "event_end_time", "event_ended_at"),
    ("alert_event", "diagnosis_refresh_needed", "is_diagnosis_refresh_needed"),
)

DROP_FK_TABLES = ("user_session", "doc_category", "doc_document")


async def _column_exists(db, table_name: str, column_name: str) -> bool:
    row = await db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return row.first() is not None


async def _rename_columns(db) -> int:
    changed = 0
    for table_name, old_name, new_name in RENAME_COLUMNS:
        old_exists = await _column_exists(db, table_name, old_name)
        new_exists = await _column_exists(db, table_name, new_name)
        if not old_exists or new_exists:
            continue
        await db.execute(
            text(f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"')
        )
        changed += 1
    return changed


async def _drop_foreign_keys(db) -> int:
    changed = 0
    for table_name in DROP_FK_TABLES:
        constraints = await db.execute(
            text(
                """
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class tbl ON tbl.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
                WHERE con.contype = 'f'
                  AND ns.nspname = current_schema()
                  AND tbl.relname = :table_name
                """
            ),
            {"table_name": table_name},
        )
        for (constraint_name,) in constraints.fetchall():
            await db.execute(
                text(
                    f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                )
            )
            changed += 1
    return changed


async def _drop_diagnosis_event_soft_delete(db) -> int:
    changed = 0
    for column_name in ("is_deleted", "deleted_at", "deleted_by"):
        if await _column_exists(db, "diagnosis_event", column_name):
            await db.execute(
                text(f'ALTER TABLE "diagnosis_event" DROP COLUMN "{column_name}"')
            )
            changed += 1
    return changed


async def _ensure_audit_timestamps(db) -> int:
    changed = 0
    for table_name in ALL_TABLES:
        if not await _column_exists(db, table_name, "created_at"):
            await db.execute(
                text(
                    f'ALTER TABLE "{table_name}" ADD COLUMN "created_at" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP'
                )
            )
            changed += 1
        await db.execute(
            text(
                f"""
                UPDATE "{table_name}"
                SET "created_at" = CURRENT_TIMESTAMP
                WHERE "created_at" IS NULL
                """
            )
        )
        await db.execute(
            text(
                f"""
                ALTER TABLE "{table_name}"
                ALTER COLUMN "created_at" SET DEFAULT CURRENT_TIMESTAMP,
                ALTER COLUMN "created_at" SET NOT NULL
                """
            )
        )

        if not await _column_exists(db, table_name, "updated_at"):
            await db.execute(
                text(
                    f'ALTER TABLE "{table_name}" ADD COLUMN "updated_at" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP'
                )
            )
            changed += 1
        await db.execute(
            text(
                f"""
                UPDATE "{table_name}"
                SET "updated_at" = COALESCE("updated_at", "created_at", CURRENT_TIMESTAMP)
                WHERE "updated_at" IS NULL
                """
            )
        )
        await db.execute(
            text(
                f"""
                ALTER TABLE "{table_name}"
                ALTER COLUMN "updated_at" SET DEFAULT CURRENT_TIMESTAMP,
                ALTER COLUMN "updated_at" SET NOT NULL
                """
            )
        )
    return changed


async def migrate(max_retries: int = 3) -> None:
    for attempt in range(1, max_retries + 1):
        async with async_session() as db:
            try:
                renamed = await _rename_columns(db)
                dropped_fk = await _drop_foreign_keys(db)
                dropped_soft_delete = await _drop_diagnosis_event_soft_delete(db)
                ensured_audit = await _ensure_audit_timestamps(db)
                await db.commit()
                logger.info(
                    "Schema normalization completed: renamed=%s dropped_fk=%s dropped_soft_delete=%s ensured_audit=%s",
                    renamed,
                    dropped_fk,
                    dropped_soft_delete,
                    ensured_audit,
                )
                return
            except Exception as exc:
                await db.rollback()
                if "deadlock detected" in str(exc).lower() and attempt < max_retries:
                    logger.warning(
                        "schema normalization deadlocked on attempt %s/%s, retrying",
                        attempt,
                        max_retries,
                    )
                    await asyncio.sleep(1)
                    continue
                raise


if __name__ == "__main__":
    asyncio.run(migrate())
