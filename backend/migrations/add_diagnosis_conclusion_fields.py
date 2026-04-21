import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        columns = [
            ("run_id", "ALTER TABLE diagnosis_conclusion ADD COLUMN run_id VARCHAR(64)"),
            ("summary", "ALTER TABLE diagnosis_conclusion ADD COLUMN summary TEXT"),
            ("confidence", "ALTER TABLE diagnosis_conclusion ADD COLUMN confidence DOUBLE PRECISION"),
            ("final_markdown", "ALTER TABLE diagnosis_conclusion ADD COLUMN final_markdown TEXT"),
            ("evidence_refs", "ALTER TABLE diagnosis_conclusion ADD COLUMN evidence_refs JSON"),
            ("knowledge_refs", "ALTER TABLE diagnosis_conclusion ADD COLUMN knowledge_refs JSON"),
        ]

        for column_name, ddl in columns:
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='diagnosis_conclusion' AND column_name=:column_name"
            ), {"column_name": column_name})
            if not result.scalar_one_or_none():
                await conn.execute(text(ddl))

        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_diagnosis_conclusion_run_id ON diagnosis_conclusion(run_id)"
        ))

    logger.info("diagnosis_conclusion extra fields ready")
