"""
将模型中的 DateTime 列统一迁移为 TIMESTAMP WITH TIME ZONE（PostgreSQL）。

迁移策略：
- 仅处理显式列出的业务表/列，避免误改其他系统表。
- 仅当当前类型是 `timestamp without time zone` 时执行转换。
- 使用 `AT TIME ZONE 'UTC'` 将历史 naive 时间按 UTC 解释并转换为 timestamptz。
"""
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session

logger = logging.getLogger(__name__)


TARGET_COLUMNS: dict[str, tuple[str, ...]] = {
    "ai_model": ("created_at", "updated_at"),
    "alert_ai_evaluation_log": ("created_at",),
    "alert_ai_policy": ("compiled_at", "created_at", "updated_at"),
    "alert_ai_runtime_state": (
        "cooldown_until",
        "last_ai_evaluated_at",
        "last_evaluated_at",
        "last_triggered_at",
        "last_recovered_at",
        "created_at",
        "updated_at",
    ),
    "alert_delivery_log": ("sent_at", "created_at"),
    "alert_event": (
        "event_started_at",
        "event_ended_at",
        "updated_at",
        "last_diagnosis_requested_at",
        "diagnosis_started_at",
        "diagnosis_completed_at",
    ),
    "alert_message": ("acknowledged_at", "resolved_at", "notified_at", "created_at", "updated_at"),
    "alert_subscription": ("created_at", "updated_at"),
    "alert_template": ("created_at", "updated_at"),
    "chat_channel_binding": ("last_message_at", "created_at", "updated_at"),
    "chat_event_dedup": ("processed_at", "created_at", "updated_at"),
    "datasource": ("silence_until", "connection_checked_at", "created_at", "updated_at"),
    "diagnosis_conclusion": ("resolved_at", "created_at", "updated_at"),
    "diagnosis_event": ("created_at", "updated_at"),
    "diagnostic_session": ("created_at", "updated_at"),
    "chat_message": ("created_at",),
    "doc_category": ("created_at",),
    "doc_document": ("compiled_at", "created_at", "updated_at"),
    "host": ("config_collected_at", "created_at", "updated_at"),
    "host_metric": ("collected_at", "created_at", "updated_at"),
    "inspection_config": ("last_scheduled_at", "next_scheduled_at", "created_at", "updated_at"),
    "inspection_trigger": ("triggered_at", "created_at", "updated_at"),
    "integration_bot_binding": ("created_at", "updated_at"),
    "integration": ("last_run_at", "created_at", "updated_at"),
    "integration_execution_log": ("created_at", "updated_at"),
    "login_log": ("logged_in_at", "created_at", "updated_at"),
    "metric_baseline_profile": ("last_snapshot_at", "created_at", "updated_at"),
    "datasource_metric": ("collected_at",),
    "report": ("created_at", "updated_at", "completed_at"),
    "system_config": ("created_at", "updated_at"),
    "user_session": ("created_at", "last_seen_at", "expires_at", "revoked_at"),
    "user": ("password_changed_at", "created_at", "updated_at"),
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
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = :table_name
                          AND column_name = :column_name
                        """
                    ),
                    {"table_name": table_name, "column_name": column_name},
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
                        "Skip %s.%s: unexpected type %s",
                        table_name,
                        column_name,
                        data_type,
                    )
                    skipped += 1
                    continue

                # 按 UTC 解释历史 naive 时间，转换为 timestamptz。
                await db.execute(
                    text(
                        f"""
                        ALTER TABLE "{table_name}"
                        ALTER COLUMN "{column_name}"
                        TYPE TIMESTAMP WITH TIME ZONE
                        USING "{column_name}" AT TIME ZONE 'UTC'
                        """
                    )
                )
                changed += 1

        await db.commit()
        logger.info(
            "Datetime timezone migration completed: changed=%s skipped=%s",
            changed,
            skipped,
        )


if __name__ == "__main__":
    asyncio.run(migrate())
