import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS diagnosis_events (
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
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnosis_events_session_id ON diagnosis_events(session_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnosis_events_run_id ON diagnosis_events(run_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnosis_events_event_type ON diagnosis_events(event_type)"))
    logger.info("diagnosis_events table ready")
