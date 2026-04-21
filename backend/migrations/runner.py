import importlib
import io
import logging
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)

MIGRATION_LOCK_KEY = 48203117
MIGRATION_TABLE_NAME = "startup_migration"
LEGACY_MIGRATION_TABLE_NAME = "startup_migrations"


@dataclass(frozen=True)
class MigrationSpec:
    name: str
    module_path: str
    function_name: str = "migrate"


PRE_CREATE_MIGRATIONS = (
    MigrationSpec(
        name="rename_legacy_log_tables_to_plural",
        module_path="backend.migrations.rename_legacy_log_tables_to_plural",
    ),
    MigrationSpec(
        name="rename_tables_to_singular",
        module_path="backend.migrations.rename_tables_to_singular",
    ),
)


POST_CREATE_MIGRATIONS = (
    MigrationSpec("add_soft_delete_columns", "backend.migrations.add_soft_delete_columns"),
    MigrationSpec("add_datasource_connection_status", "backend.migrations.add_datasource_connection_status"),
    MigrationSpec("add_datasource_tags", "backend.migrations.add_datasource_tags"),
    MigrationSpec("add_alert_notified_at", "backend.migrations.add_alert_notified_at"),
    MigrationSpec("replace_knowledge_base_with_documents", "backend.migrations.replace_knowledge_base_with_documents"),
    MigrationSpec("add_ai_model_context_window", "backend.migrations.add_ai_model_context_window"),
    MigrationSpec("normalize_ai_model_timestamps", "backend.migrations.normalize_ai_model_timestamps"),
    MigrationSpec("add_diagnostic_session_token_usage", "backend.migrations.add_diagnostic_session_token_usage"),
    MigrationSpec("add_chat_message_token_usage", "backend.migrations.add_chat_message_token_usage"),
    MigrationSpec("add_chat_message_render_segments", "backend.migrations.add_chat_message_render_segments"),
    MigrationSpec("add_report_alert_link", "backend.migrations.add_report_alert_link"),
    MigrationSpec("add_trigger_alert_link", "backend.migrations.add_trigger_alert_link"),
    MigrationSpec("add_user_session_security", "backend.migrations.add_user_session_security"),
    MigrationSpec("add_feishu_chat_tables", "backend.migrations.add_feishu_chat_tables"),
    MigrationSpec("fix_feishu_chat_event_dedups_duplicates", "backend.migrations.fix_feishu_chat_event_dedups_duplicates"),
    MigrationSpec("create_diagnosis_events", "backend.migrations.create_diagnosis_events"),
    MigrationSpec("add_diagnosis_event_soft_delete", "backend.migrations.add_diagnosis_event_soft_delete"),
    MigrationSpec("create_diagnosis_conclusions", "backend.migrations.create_diagnosis_conclusions"),
    MigrationSpec("add_subscription_integration_targets", "backend.migrations.add_subscription_integration_targets"),
    MigrationSpec("add_datasource_inbound_source", "backend.migrations.add_datasource_inbound_source"),
    MigrationSpec(
        "add_diagnostic_session_hidden_and_alert_diagnosis",
        "backend.migrations.add_diagnostic_session_hidden_and_alert_diagnosis",
    ),
    MigrationSpec(
        "add_diagnostic_session_skill_authorizations",
        "backend.migrations.add_diagnostic_session_skill_authorizations",
    ),
    MigrationSpec("add_bot_bindings", "backend.migrations.add_bot_bindings"),
    MigrationSpec(
        "extend_integration_execution_logs_for_targets",
        "backend.migrations.extend_integration_execution_logs_for_targets",
    ),
    MigrationSpec(
        "extend_alert_delivery_logs_targets",
        "backend.migrations.extend_alert_delivery_logs_targets",
    ),
    MigrationSpec("add_alert_ai_diagnosis_summary", "backend.migrations.add_alert_ai_diagnosis_summary"),
    MigrationSpec("add_alert_event_diagnosis_fields", "backend.migrations.add_alert_event_diagnosis_fields"),
    MigrationSpec("add_knowledge_routing_fields", "backend.migrations.add_knowledge_routing_fields"),
    MigrationSpec("add_document_compilation_fields", "backend.migrations.add_document_compilation_fields"),
    MigrationSpec(
        "add_alert_event_diagnosis_timestamps",
        "backend.migrations.add_alert_event_diagnosis_timestamps",
    ),
    MigrationSpec("add_alert_ai_engine", "backend.migrations.add_alert_ai_engine"),
    MigrationSpec("add_alert_templates", "backend.migrations.add_alert_templates"),
    MigrationSpec("add_alert_ai_candidate_gating", "backend.migrations.add_alert_ai_candidate_gating"),
    MigrationSpec("add_baseline_and_event_strategy", "backend.migrations.add_baseline_and_event_strategy"),
    MigrationSpec(
        "rebind_inspection_configs_to_default_template",
        "backend.migrations.rebind_inspection_configs_to_default_template",
    ),
    MigrationSpec(
        "add_metric_composite_index",
        "backend.migrations.add_metric_composite_index",
        function_name="add_composite_index",
    ),
    MigrationSpec("add_reports_indexes", "backend.migrations.add_reports_indexes"),
    MigrationSpec(
        "archive_and_drop_deprecated_report_columns",
        "backend.migrations.archive_and_drop_deprecated_report_columns",
    ),
    MigrationSpec("add_schema_hardening_indexes", "backend.migrations.add_schema_hardening_indexes"),
    MigrationSpec("normalize_core_foreign_keys", "backend.migrations.normalize_core_foreign_keys"),
    MigrationSpec(
        "migrate_alert_channels_to_subscription_targets",
        "backend.migrations.migrate_alert_channels_to_subscription_targets",
    ),
    MigrationSpec(
        "migrate_inbound_integrations_to_datasource_sources",
        "backend.migrations.migrate_inbound_integrations_to_datasource_sources",
    ),
    MigrationSpec(
        "migrate_datasource_extra_params_to_jsonb",
        "backend.migrations.migrate_datasource_extra_params_to_jsonb",
    ),
    MigrationSpec(
        "migrate_feishu_bot_channel_to_bot_binding",
        "backend.migrations.migrate_feishu_bot_channel_to_bot_binding",
    ),
    MigrationSpec(
        "migrate_integration_datasource_metrics_to_db_status",
        "backend.migrations.migrate_integration_datasource_metrics_to_db_status",
    ),
    MigrationSpec(
        "drop_legacy_alert_channel_schema",
        "backend.migrations.drop_legacy_alert_channel_schema",
    ),
    MigrationSpec("archive_legacy_adapter_schema", "backend.migrations.archive_legacy_adapter_schema"),
    MigrationSpec(
        "remove_datasource_monitoring_intervals",
        "backend.migrations.remove_datasource_monitoring_intervals",
    ),
    MigrationSpec("add_ssh_agent_auth", "backend.migrations.add_ssh_agent_auth"),
    MigrationSpec("add_host_os_version", "backend.migrations.add_host_os_version"),
    MigrationSpec("add_host_config_cache", "backend.migrations.add_host_config_cache"),
    MigrationSpec("add_host_id_to_diagnostic_sessions", "backend.migrations.add_host_id_to_diagnostic_sessions"),
    MigrationSpec(
        "migrate_models_datetime_to_timestamptz",
        "backend.migrations.migrate_models_datetime_to_timestamptz",
    ),
    MigrationSpec(
        "migrate_float_columns_to_numeric_22_4",
        "backend.migrations.migrate_float_columns_to_numeric_22_4",
    ),
    MigrationSpec(
        "ensure_inspection_trigger_datasource_metric",
        "backend.migrations.ensure_inspection_trigger_datasource_metric",
    ),
    MigrationSpec(
        "alter_metric_tables_pk_to_bigint",
        "backend.migrations.alter_metric_tables_pk_to_bigint",
    ),
    MigrationSpec(
        "alter_large_volume_ids_to_bigint",
        "backend.migrations.alter_large_volume_ids_to_bigint",
    ),
    MigrationSpec(
        "alter_log_table_ids_to_bigint",
        "backend.migrations.alter_log_table_ids_to_bigint",
    ),
    MigrationSpec(
        "migrate_jsonb_columns_to_json",
        "backend.migrations.migrate_jsonb_columns_to_json",
    ),
    MigrationSpec(
        "fix_soft_delete_deleted_at_timezone",
        "backend.migrations.fix_soft_delete_deleted_at_timezone",
    ),
    MigrationSpec(
        "normalize_skill_model_columns",
        "backend.migrations.normalize_skill_model_columns",
    ),
    MigrationSpec(
        "normalize_schema_p0_p1_and_audit_timestamps",
        "backend.migrations.normalize_schema_p0_p1_and_audit_timestamps",
    ),
    MigrationSpec(
        "fix_alert_event_last_updated_column",
        "backend.migrations.fix_alert_event_last_updated_column",
    ),
    MigrationSpec(
        "ensure_diagnosis_event_soft_delete_columns",
        "backend.migrations.ensure_diagnosis_event_soft_delete_columns",
    ),
)


async def run_pre_create_migrations() -> None:
    await _run_migrations("pre-create", PRE_CREATE_MIGRATIONS)


async def run_post_create_migrations() -> None:
    await _run_migrations("post-create", POST_CREATE_MIGRATIONS)


def _load_callable(spec: MigrationSpec):
    module = importlib.import_module(spec.module_path)
    return getattr(module, spec.function_name)


@contextmanager
def _suppress_migration_noise():
    migration_logger = logging.getLogger("backend.migrations")
    previous_level = migration_logger.level
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    try:
        migration_logger.setLevel(logging.WARNING)
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            yield stdout_buffer, stderr_buffer
    finally:
        migration_logger.setLevel(previous_level)


async def _ensure_migration_table(conn) -> None:
    legacy_exists = await conn.execute(
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
        {"table_name": LEGACY_MIGRATION_TABLE_NAME},
    )
    current_exists = await conn.execute(
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
        {"table_name": MIGRATION_TABLE_NAME},
    )
    if bool(legacy_exists.scalar_one()) and not bool(current_exists.scalar_one()):
        await conn.execute(
            text(
                f'ALTER TABLE "{LEGACY_MIGRATION_TABLE_NAME}" RENAME TO "{MIGRATION_TABLE_NAME}"'
            )
        )

    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE_NAME} (
                name VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    applied_at_type = await conn.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = 'applied_at'
            """
        ),
        {"table_name": MIGRATION_TABLE_NAME},
    )
    if applied_at_type.scalar_one_or_none() == "timestamp without time zone":
        await conn.execute(
            text(
                f"""
                ALTER TABLE {MIGRATION_TABLE_NAME}
                ALTER COLUMN applied_at TYPE TIMESTAMPTZ USING applied_at AT TIME ZONE 'UTC'
                """
            )
        )

    await conn.execute(
        text(
            f"""
            ALTER TABLE {MIGRATION_TABLE_NAME}
            ALTER COLUMN applied_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN applied_at SET NOT NULL
            """
        )
    )


async def _load_applied_migrations(conn) -> set[str]:
    result = await conn.execute(text(f"SELECT name FROM {MIGRATION_TABLE_NAME}"))
    return {row[0] for row in result.fetchall()}


async def _record_migration(conn, migration_name: str) -> None:
    await conn.execute(
        text(
            f"""
            INSERT INTO {MIGRATION_TABLE_NAME} (name)
            VALUES (:name)
            ON CONFLICT (name) DO NOTHING
            """
        ),
        {"name": migration_name},
    )


async def _run_migrations(stage: str, migrations: tuple[MigrationSpec, ...]) -> None:
    applied_count = 0
    skipped_count = 0
    failed_count = 0

    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        await conn.commit()
        try:
            await _ensure_migration_table(conn)
            applied = await _load_applied_migrations(conn)
            await conn.commit()

            for spec in migrations:
                if spec.name in applied:
                    skipped_count += 1
                    continue

                migration_callable = _load_callable(spec)
                try:
                    with _suppress_migration_noise() as (stdout_buffer, stderr_buffer):
                        await migration_callable()
                except Exception as exc:
                    failed_count += 1
                    suppressed_output = "\n".join(
                        segment.strip()
                        for segment in (stdout_buffer.getvalue(), stderr_buffer.getvalue())
                        if segment.strip()
                    )
                    if suppressed_output:
                        logger.warning(
                            "Startup migration failed [%s]: %s | captured_output=%s",
                            spec.name,
                            exc,
                            suppressed_output,
                        )
                    else:
                        logger.warning("Startup migration failed [%s]: %s", spec.name, exc)
                    continue

                await _record_migration(conn, spec.name)
                await conn.commit()
                applied.add(spec.name)
                applied_count += 1
        finally:
            # 若前面任一步 SQL 失败，连接会处于 aborted transaction 状态；
            # 先回滚再释放 advisory lock，避免 unlock 自身也报错。
            await conn.rollback()
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            await conn.commit()

    if applied_count or failed_count:
        logger.info(
            "Startup %s migrations synchronized: applied=%s skipped=%s failed=%s",
            stage,
            applied_count,
            skipped_count,
            failed_count,
        )
