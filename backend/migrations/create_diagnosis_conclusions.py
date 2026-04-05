"""Create diagnosis_conclusions table"""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def migrate():
    """Create diagnosis_conclusions table"""
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name='diagnosis_conclusions'"))
        if result.scalar_one_or_none():
            print("Table diagnosis_conclusions already exists, skipping")
            return

        await conn.execute(text("""
            CREATE TABLE diagnosis_conclusions (
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
        await conn.execute(text("CREATE INDEX ix_diagnosis_conclusions_session ON diagnosis_conclusions(session_id)"))
        await conn.execute(text("CREATE INDEX ix_diagnosis_conclusions_run_id ON diagnosis_conclusions(run_id)"))
        print("Created diagnosis_conclusions table")