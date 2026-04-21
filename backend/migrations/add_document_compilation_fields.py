"""Add document compilation fields for knowledge orchestration."""
import asyncio

from sqlalchemy import text

from backend.database import engine


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE doc_document
            ADD COLUMN IF NOT EXISTS diagnosis_profile JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_document
            ADD COLUMN IF NOT EXISTS compiled_snapshot JSON
        """))
        await conn.execute(text("""
            ALTER TABLE doc_document
            ADD COLUMN IF NOT EXISTS compiled_at TIMESTAMP NULL
        """))
        await conn.execute(text("""
            ALTER TABLE doc_document
            ADD COLUMN IF NOT EXISTS quality_status VARCHAR(20) DEFAULT 'draft'
        """))
        await conn.execute(text("""
            UPDATE doc_document
            SET diagnosis_profile = COALESCE(
                diagnosis_profile,
                json_build_object(
                    'symptom_tags', '[]'::json,
                    'signal_tags', '[]'::json,
                    'recommended_skills', '[]'::json,
                    'applicability_rules', '[]'::json,
                    'evidence_requirements', '[]'::json,
                    'related_doc_ids', '[]'::json
                )
            )
        """))
        await conn.execute(text("""
            UPDATE doc_document
            SET quality_status = COALESCE(
                quality_status,
                CASE
                    WHEN freshness_level = 'expired' THEN 'expired'
                    ELSE 'draft'
                END
            )
        """))


if __name__ == "__main__":
    asyncio.run(migrate())
