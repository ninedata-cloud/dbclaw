"""Create diagnosis_conclusion table"""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def migrate():
    """Create diagnosis_conclusion table"""
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'diagnosis_conclusion'
        """))
        if result.scalar_one_or_none():
            print("Table diagnosis_conclusion already exists, skipping")
            return

        await conn.execute(text("""
            CREATE TABLE diagnosis_conclusion (
                id SERIAL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                datasource_id INTEGER,
                run_id VARCHAR(64),
                summary TEXT,
                confidence DOUBLE PRECISION,
                final_markdown TEXT,
                findings JSON,
                action_items JSON,
                evidence_refs JSON,
                knowledge_refs JSON,
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP,
                resolved_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("CREATE INDEX ix_diagnosis_conclusion_session ON diagnosis_conclusion(session_id)"))
        await conn.execute(text("CREATE INDEX ix_diagnosis_conclusion_run_id ON diagnosis_conclusion(run_id)"))
        print("Created diagnosis_conclusion table")
