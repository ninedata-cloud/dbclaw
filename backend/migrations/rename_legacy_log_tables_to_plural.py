import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


TABLE_RENAMES = [
    {
        "old_table": "alert_delivery_log",
        "new_table": "alert_delivery_logs",
        "sequence": ("alert_delivery_log_id_seq", "alert_delivery_logs_id_seq"),
        "indexes": [
            ("alert_delivery_log_pkey", "alert_delivery_logs_pkey"),
            ("ix_alert_delivery_log_alert_id", "ix_alert_delivery_logs_alert_id"),
            ("ix_alert_delivery_log_created_at", "ix_alert_delivery_logs_created_at"),
            ("ix_alert_delivery_log_id", "ix_alert_delivery_logs_id"),
            ("ix_alert_delivery_log_integration_id", "ix_alert_delivery_logs_integration_id"),
            ("ix_alert_delivery_log_status", "ix_alert_delivery_logs_status"),
            ("ix_alert_delivery_log_subscription_id", "ix_alert_delivery_logs_subscription_id"),
            ("ix_alert_delivery_log_target_id", "ix_alert_delivery_logs_target_id"),
        ],
    },
    {
        "old_table": "chat_event_dedup",
        "new_table": "chat_event_dedups",
        "sequence": ("chat_event_dedup_id_seq", "chat_event_dedups_id_seq"),
        "indexes": [
            ("chat_event_dedup_pkey", "chat_event_dedups_pkey"),
            ("ix_chat_event_dedup_channel_type", "ix_chat_event_dedups_channel_type"),
            ("ix_chat_event_dedup_event_type", "ix_chat_event_dedups_event_type"),
            ("ix_chat_event_dedup_external_event_id", "ix_chat_event_dedups_external_event_id"),
            ("ix_chat_event_dedup_external_message_id", "ix_chat_event_dedups_external_message_id"),
            ("uq_chat_event_dedup_event_id", "uq_chat_event_dedups_event_id"),
            ("uq_chat_event_dedup_message_id", "uq_chat_event_dedups_message_id"),
        ],
    },
]


async def _table_exists(conn, table_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar_one())


async def _rename_index_if_exists(conn, old_name: str, new_name: str) -> None:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname = :index_name
            )
            """
        ),
        {"index_name": old_name},
    )
    if result.scalar_one():
        await conn.execute(text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


async def _rename_sequence_if_exists(conn, old_name: str, new_name: str) -> None:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.sequences
                WHERE sequence_schema = current_schema()
                  AND sequence_name = :sequence_name
            )
            """
        ),
        {"sequence_name": old_name},
    )
    if result.scalar_one():
        await conn.execute(text(f'ALTER SEQUENCE "{old_name}" RENAME TO "{new_name}"'))


async def migrate():
    renamed_any = False
    async with get_engine().begin() as conn:
        for spec in TABLE_RENAMES:
            old_table = spec["old_table"]
            new_table = spec["new_table"]

            if not await _table_exists(conn, old_table):
                continue
            if await _table_exists(conn, new_table):
                logger.info("Skip renaming %s because %s already exists", old_table, new_table)
                continue

            logger.info("Renaming %s to %s", old_table, new_table)
            await conn.execute(text(f'ALTER TABLE "{old_table}" RENAME TO "{new_table}"'))
            await _rename_sequence_if_exists(conn, *spec["sequence"])
            for old_index, new_index in spec["indexes"]:
                await _rename_index_if_exists(conn, old_index, new_index)
            renamed_any = True

    if renamed_any:
        logger.info("Legacy log tables renamed to plural form")
