"""Rename legacy plural table names to singular names."""

import asyncio

from sqlalchemy import text

from backend.database import async_session


TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("metric_baseline_profiles", "metric_baseline_profile"),
    ("inspection_configs", "inspection_config"),
    ("alert_ai_policies", "alert_ai_policy"),
    ("integration_bot_bindings", "integration_bot_binding"),
    ("hosts", "host"),
    ("integrations", "integration"),
    ("integration_execution_logs", "integration_execution_log"),
    ("chat_event_dedups", "chat_event_dedup"),
    ("alert_ai_runtime_states", "alert_ai_runtime_state"),
    ("alert_ai_evaluation_logs", "alert_ai_evaluation_log"),
    ("datasource_metrics", "datasource_metric"),
    ("inspection_triggers", "inspection_trigger"),
    ("alert_events", "alert_event"),
    ("diagnostic_sessions", "diagnostic_session"),
    ("chat_messages", "chat_message"),
    ("doc_categories", "doc_category"),
    ("doc_documents", "doc_document"),
    ("diagnosis_events", "diagnosis_event"),
    ("system_configs", "system_config"),
    ("alert_templates", "alert_template"),
    ("datasources", "datasource"),
    ("host_metrics", "host_metric"),
    ("ai_models", "ai_model"),
    ("alert_messages", "alert_message"),
    ("alert_delivery_logs", "alert_delivery_log"),
    ("user_sessions", "user_session"),
    ("reports", "report"),
    ("login_logs", "login_log"),
    ("chat_channel_bindings", "chat_channel_binding"),
    ("alert_subscriptions", "alert_subscription"),
    ("diagnosis_conclusions", "diagnosis_conclusion"),
    ("users", "user"),
    ("skills", "skill"),
    ("skill_executions", "skill_execution"),
    ("skill_ratings", "skill_rating"),
)


async def _table_exists(db, table_name: str) -> bool:
    result = await db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            LIMIT 1
            """
        ),
        {"table_name": table_name},
    )
    return result.scalar_one_or_none() is not None


async def migrate() -> None:
    async with async_session() as db:
        for old_name, new_name in TABLE_RENAMES:
            old_exists = await _table_exists(db, old_name)
            if not old_exists:
                continue

            new_exists = await _table_exists(db, new_name)
            if new_exists:
                continue

            await db.execute(text(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"'))

        await db.commit()


if __name__ == "__main__":
    asyncio.run(migrate())
