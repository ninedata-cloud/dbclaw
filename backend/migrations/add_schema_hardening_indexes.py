import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


INDEX_STATEMENTS = {
    "idx_host_metrics_host_id_collected_at": """
        CREATE INDEX IF NOT EXISTS idx_host_metrics_host_id_collected_at
        ON host_metrics(host_id, collected_at DESC)
    """,
    "idx_alert_messages_event_created_at": """
        CREATE INDEX IF NOT EXISTS idx_alert_messages_event_created_at
        ON alert_messages(event_id, created_at DESC)
    """,
    "idx_alert_messages_status_created_at_id": """
        CREATE INDEX IF NOT EXISTS idx_alert_messages_status_created_at_id
        ON alert_messages(status, created_at DESC, id DESC)
    """,
    "idx_diagnosis_events_session_run_sequence_id": """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_events_session_run_sequence_id
        ON diagnosis_events(session_id, run_id, sequence_no, id)
    """,
    "idx_diagnosis_conclusions_session_updated_at_id": """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_conclusions_session_updated_at_id
        ON diagnosis_conclusions(session_id, updated_at DESC, id DESC)
    """,
    "idx_doc_categories_parent_sort": """
        CREATE INDEX IF NOT EXISTS idx_doc_categories_parent_sort
        ON doc_categories(parent_id, sort_order)
    """,
    "idx_doc_documents_category_active_sort": """
        CREATE INDEX IF NOT EXISTS idx_doc_documents_category_active_sort
        ON doc_documents(category_id, is_active, is_deleted, sort_order)
    """,
    "idx_skill_executions_skill_id_created_at": """
        CREATE INDEX IF NOT EXISTS idx_skill_executions_skill_id_created_at
        ON skill_executions(skill_id, created_at DESC)
    """,
    "uq_skill_ratings_skill_user": """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_ratings_skill_user
        ON skill_ratings(skill_id, user_id)
    """,
    "uq_chat_channel_bindings_channel_chat_user": """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_channel_bindings_channel_chat_user
        ON chat_channel_bindings(channel_type, external_chat_id, COALESCE(external_user_id, ''))
    """,
}


async def _table_exists(conn, table_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar_one())


async def migrate():
    engine = get_engine()

    async with engine.begin() as conn:
        if await _table_exists(conn, "skill_ratings"):
            await conn.execute(
                text(
                    """
                    DELETE FROM skill_ratings older
                    USING skill_ratings newer
                    WHERE older.id < newer.id
                      AND older.skill_id = newer.skill_id
                      AND older.user_id = newer.user_id
                    """
                )
            )

        if await _table_exists(conn, "chat_channel_bindings"):
            await conn.execute(
                text(
                    """
                    DELETE FROM chat_channel_bindings older
                    USING chat_channel_bindings newer
                    WHERE older.id < newer.id
                      AND older.channel_type = newer.channel_type
                      AND older.external_chat_id = newer.external_chat_id
                      AND COALESCE(older.external_user_id, '') = COALESCE(newer.external_user_id, '')
                    """
                )
            )

    async with engine.begin() as conn:
        existing_tables = {
            table_name
            for (table_name,) in (
                await conn.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = current_schema()
                        """
                    )
                )
            ).all()
        }

        for index_name, sql in INDEX_STATEMENTS.items():
            target_table = sql.split("ON ", 1)[1].split("(", 1)[0].strip()
            if target_table not in existing_tables:
                logger.info("Skip index %s because table %s does not exist", index_name, target_table)
                continue
            logger.info("Ensuring index: %s", index_name)
            await conn.execute(text(sql))

    logger.info("Schema hardening indexes ensured")
