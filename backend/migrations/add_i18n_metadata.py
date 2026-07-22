"""Add locale/time-zone metadata used by system-generated content.

The migration is deliberately additive and idempotent. Existing natural-language
content is preserved; known built-in/system content is labelled instead of being
machine translated.
"""

import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def upgrade():
    engine = get_engine()
    async with engine.begin() as conn:
        statements = (
            "ALTER TABLE app_user ALTER COLUMN locale TYPE VARCHAR(35)",
            "ALTER TABLE app_user ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'",
            "ALTER TABLE report ADD COLUMN IF NOT EXISTS generation_locale VARCHAR(35) NOT NULL DEFAULT 'zh-CN'",
            "ALTER TABLE report ADD COLUMN IF NOT EXISTS generation_timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'",
            "ALTER TABLE inspection_trigger ADD COLUMN IF NOT EXISTS requested_locale VARCHAR(35) NOT NULL DEFAULT 'zh-CN'",
            "ALTER TABLE inspection_trigger ADD COLUMN IF NOT EXISTS requested_timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'",
            "ALTER TABLE alert_message ADD COLUMN IF NOT EXISTS message_code VARCHAR(120)",
            "ALTER TABLE alert_message ADD COLUMN IF NOT EXISTS message_params JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE alert_message ADD COLUMN IF NOT EXISTS content_locale VARCHAR(35) NOT NULL DEFAULT 'zh-CN'",
            "ALTER TABLE alert_event ADD COLUMN IF NOT EXISTS diagnosis_locale VARCHAR(35)",
            "ALTER TABLE alert_subscription ADD COLUMN IF NOT EXISTS locale VARCHAR(35)",
            "ALTER TABLE alert_subscription ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)",
            "ALTER TABLE alert_delivery_log ADD COLUMN IF NOT EXISTS rendered_locale VARCHAR(35)",
            "ALTER TABLE alert_delivery_log ADD COLUMN IF NOT EXISTS rendered_timezone VARCHAR(64)",
            "ALTER TABLE diagnostic_session ADD COLUMN IF NOT EXISTS default_locale VARCHAR(35) NOT NULL DEFAULT 'zh-CN'",
            "ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS content_locale VARCHAR(35) NOT NULL DEFAULT 'und'",
            "ALTER TABLE doc_category ADD COLUMN IF NOT EXISTS code VARCHAR(100)",
            "ALTER TABLE doc_document ADD COLUMN IF NOT EXISTS content_locale VARCHAR(35) NOT NULL DEFAULT 'und'",
            "ALTER TABLE doc_document ADD COLUMN IF NOT EXISTS translation_group_id VARCHAR(100)",
            "ALTER TABLE chat_channel_binding ADD COLUMN IF NOT EXISTS locale VARCHAR(35)",
            "ALTER TABLE chat_channel_binding ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)",
            "ALTER TABLE skill ADD COLUMN IF NOT EXISTS content_locale VARCHAR(35) NOT NULL DEFAULT 'und'",
            "ALTER TABLE skill ADD COLUMN IF NOT EXISTS i18n JSONB NOT NULL DEFAULT '{}'::jsonb",
            "CREATE INDEX IF NOT EXISTS idx_alert_message_message_code ON alert_message (message_code)",
            "CREATE INDEX IF NOT EXISTS idx_doc_category_code ON doc_category (code)",
            "CREATE INDEX IF NOT EXISTS idx_doc_document_content_locale ON doc_document (content_locale)",
            "CREATE INDEX IF NOT EXISTS idx_doc_document_translation_group_id ON doc_document (translation_group_id)",
        )
        for statement in statements:
            await conn.execute(text(statement))

        await conn.execute(text("""
            UPDATE doc_document
            SET content_locale = CASE WHEN is_builtin THEN 'zh-CN' ELSE 'und' END
            WHERE content_locale IS NULL OR content_locale = 'und'
        """))
        await conn.execute(text("""
            UPDATE doc_document
            SET translation_group_id = 'builtin:legacy:' || id::text
            WHERE is_builtin = TRUE AND translation_group_id IS NULL
        """))
        await conn.execute(text("""
            UPDATE doc_category
            SET code = CASE
                WHEN parent_id IS NULL THEN 'database.' || db_type
                WHEN name = '综合诊断' THEN 'scenario.general-diagnostics'
                WHEN name = '性能诊断' THEN 'scenario.performance-diagnostics'
                WHEN name = '故障排查' THEN 'scenario.troubleshooting'
                WHEN name = '配置与会话' THEN 'scenario.configuration-sessions'
                WHEN name = '安全与权限' THEN 'scenario.security-permissions'
                WHEN name = '技术参考' THEN 'scenario.technical-reference'
                ELSE 'category.' || id::text
            END
            WHERE code IS NULL
        """))
        await conn.execute(text("""
            UPDATE alert_event
            SET diagnosis_locale = 'zh-CN'
            WHERE diagnosis_locale IS NULL
              AND (ai_diagnosis_summary IS NOT NULL OR root_cause IS NOT NULL OR recommended_actions IS NOT NULL)
        """))
        await conn.execute(text("""
            UPDATE skill
            SET content_locale = CASE WHEN is_builtin THEN 'en-US' ELSE 'und' END
            WHERE content_locale IS NULL OR content_locale = 'und'
        """))
        await conn.execute(text("""
            INSERT INTO system_config
                (key, value, value_type, description, category, is_active, is_encrypted)
            VALUES
                ('i18n.default_locale', 'zh-CN', 'string', 'Default application locale', 'i18n', TRUE, FALSE),
                ('i18n.default_timezone', 'Asia/Shanghai', 'string', 'Default application time zone', 'i18n', TRUE, FALSE)
            ON CONFLICT (key) DO NOTHING
        """))

    logger.info("Ensured internationalization metadata columns and defaults")


async def downgrade():
    """Compatibility migration: intentionally keep additive metadata on downgrade."""
    logger.warning("add_i18n_metadata downgrade is intentionally non-destructive")
