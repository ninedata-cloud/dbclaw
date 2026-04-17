import importlib
import io
import logging
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)

MIGRATION_LOCK_KEY = 48203117


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
    MigrationSpec(
        "rebind_inspection_configs_to_default_template",
        "backend.migrations.rebind_inspection_configs_to_default_template",
    ),
    MigrationSpec("add_alert_ai_candidate_gating", "backend.migrations.add_alert_ai_candidate_gating"),
    MigrationSpec("add_baseline_and_event_strategy", "backend.migrations.add_baseline_and_event_strategy"),
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
        "migrate_integration_metric_snapshots_to_db_status",
        "backend.migrations.migrate_integration_metric_snapshots_to_db_status",
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
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS startup_migrations (
                name VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


async def _load_applied_migrations(conn) -> set[str]:
    result = await conn.execute(text("SELECT name FROM startup_migrations"))
    return {row[0] for row in result.fetchall()}


async def _record_migration(conn, migration_name: str) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO startup_migrations (name)
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
