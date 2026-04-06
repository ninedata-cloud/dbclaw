"""Add knowledge routing metadata and snapshots"""
import asyncio

from sqlalchemy import text

from backend.database import engine


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE diagnostic_sessions
            ADD COLUMN IF NOT EXISTS knowledge_snapshot JSON
        """))
        await conn.execute(text("""
            ALTER TABLE reports
            ADD COLUMN IF NOT EXISTS knowledge_sources JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS scope VARCHAR(20) DEFAULT 'builtin'
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS doc_kind VARCHAR(30) DEFAULT 'reference'
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS db_types JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS issue_categories JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS datasource_ids JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS host_ids JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS tags JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS freshness_level VARCHAR(20) DEFAULT 'stable'
        """))
        await conn.execute(text("""
            ALTER TABLE doc_documents
            ADD COLUMN IF NOT EXISTS enabled_in_diagnosis BOOLEAN DEFAULT TRUE
        """))

        await conn.execute(text("""
            UPDATE doc_documents
            SET scope = COALESCE(scope, CASE WHEN is_builtin THEN 'builtin' ELSE 'tenant' END)
        """))
        await conn.execute(text("""
            UPDATE doc_documents
            SET db_types = COALESCE(db_types, json_build_array(dc.db_type))
            FROM doc_categories dc
            WHERE dc.id = doc_documents.category_id
        """))
        await conn.execute(text("""
            UPDATE doc_documents
            SET doc_kind = COALESCE(
                doc_kind,
                CASE
                    WHEN dc.name = '技术参考' THEN 'reference'
                    WHEN dc.name = '综合诊断' THEN 'sop'
                    WHEN dc.name = '故障排查' THEN 'runbook'
                    ELSE 'runbook'
                END
            )
            FROM doc_categories dc
            WHERE dc.id = doc_documents.category_id
        """))
        await conn.execute(text("""
            UPDATE doc_documents
            SET issue_categories = COALESCE(
                issue_categories,
                CASE
                    WHEN dc.name = '性能诊断' THEN '["performance","sql","resource"]'::json
                    WHEN dc.name = '故障排查' THEN '["error","connectivity","locking","replication"]'::json
                    WHEN dc.name = '配置与会话' THEN '["configuration","connectivity"]'::json
                    WHEN dc.name = '安全与权限' THEN '["error","configuration"]'::json
                    WHEN dc.name = '综合诊断' THEN '["general","performance"]'::json
                    ELSE '["general"]'::json
                END
            )
            FROM doc_categories dc
            WHERE dc.id = doc_documents.category_id
        """))
        await conn.execute(text("""
            UPDATE doc_documents
            SET enabled_in_diagnosis = COALESCE(enabled_in_diagnosis, TRUE),
                freshness_level = COALESCE(freshness_level, 'stable'),
                priority = COALESCE(priority, 0)
        """))


if __name__ == "__main__":
    asyncio.run(migrate())
