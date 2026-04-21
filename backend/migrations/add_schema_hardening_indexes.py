import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


INDEX_STATEMENTS = {
    "idx_host_metric_host_id_collected_at": """
        CREATE INDEX IF NOT EXISTS idx_host_metric_host_id_collected_at
        ON host_metric(host_id, collected_at DESC)
    """,
    "idx_alert_message_event_created_at": """
        CREATE INDEX IF NOT EXISTS idx_alert_message_event_created_at
        ON alert_message(event_id, created_at DESC)
    """,
    "idx_alert_message_status_created_at_id": """
        CREATE INDEX IF NOT EXISTS idx_alert_message_status_created_at_id
        ON alert_message(status, created_at DESC, id DESC)
    """,
    "idx_diagnosis_event_session_run_sequence_id": """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_event_session_run_sequence_id
        ON diagnosis_event(session_id, run_id, sequence_no, id)
    """,
    "idx_diagnosis_conclusion_session_updated_at_id": """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_conclusion_session_updated_at_id
        ON diagnosis_conclusion(session_id, updated_at DESC, id DESC)
    """,
    "idx_doc_category_parent_sort": """
        CREATE INDEX IF NOT EXISTS idx_doc_category_parent_sort
        ON doc_category(parent_id, sort_order)
    """,
    "idx_doc_document_category_active_sort": """
        CREATE INDEX IF NOT EXISTS idx_doc_document_category_active_sort
        ON doc_document(category_id, is_active, is_deleted, sort_order)
    """,
    "idx_skill_executions_skill_id_created_at": """
        CREATE INDEX IF NOT EXISTS idx_skill_executions_skill_id_created_at
        ON skill_execution(skill_id, created_at DESC)
    """,
    "uq_skill_rating_skill_user": """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_rating_skill_user
        ON skill_rating(skill_id, user_id)
    """,
    "uq_chat_channel_binding_channel_chat_user": """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_channel_binding_channel_chat_user
        ON chat_channel_binding(channel_type, external_chat_id, COALESCE(external_user_id, ''))
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
        if await _table_exists(conn, "skill_rating"):
            await conn.execute(
                text(
                    """
                    DELETE FROM skill_rating older
                    USING skill_rating newer
                    WHERE older.id < newer.id
                      AND older.skill_id = newer.skill_id
                      AND older.user_id = newer.user_id
                    """
                )
            )

        if await _table_exists(conn, "chat_channel_binding"):
            await conn.execute(
                text(
                    """
                    DELETE FROM chat_channel_binding older
                    USING chat_channel_binding newer
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
