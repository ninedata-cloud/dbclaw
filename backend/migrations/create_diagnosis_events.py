import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS diagnosis_event (
                id SERIAL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                run_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                sequence_no INTEGER NOT NULL DEFAULT 0,
                step_id VARCHAR(100),
                payload JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnosis_event_session_id ON diagnosis_event(session_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnosis_event_run_id ON diagnosis_event(run_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnosis_event_event_type ON diagnosis_event(event_type)"))
    logger.info("diagnosis_event table ready")
