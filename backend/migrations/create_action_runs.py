"""Migration: create action_runs table."""

import asyncio
import logging
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'action_runs'"
        ))
        if result.scalar_one_or_none():
            logger.info("Table action_runs already exists")
            return

        await conn.execute(text(
            """
            CREATE TABLE action_runs (
                id SERIAL PRIMARY KEY,
                report_id INTEGER NOT NULL,
                alert_id INTEGER NULL,
                session_id INTEGER NULL,
                datasource_id INTEGER NOT NULL,
                recommendation_id VARCHAR(100) NOT NULL,

                title VARCHAR(255) NOT NULL,
                risk_level VARCHAR(20) NOT NULL DEFAULT 'safe',
                action_spec JSON NOT NULL,

                approval_id VARCHAR(100) NULL,
                approval_status VARCHAR(20) NOT NULL DEFAULT 'not_required',
                approved_by INTEGER NULL,
                approved_at TIMESTAMP NULL,

                skill_id VARCHAR(100) NULL,
                skill_execution_id INTEGER NULL,
                execution_status VARCHAR(30) NOT NULL DEFAULT 'pending',
                execution_result_summary TEXT NULL,

                verification_skill_id VARCHAR(100) NULL,
                verification_skill_execution_id INTEGER NULL,
                verification_status VARCHAR(30) NOT NULL DEFAULT 'not_requested',
                verification_summary TEXT NULL,

                status VARCHAR(30) NOT NULL DEFAULT 'pending_approval',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))

        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_report_id ON action_runs (report_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_alert_id ON action_runs (alert_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_session_id ON action_runs (session_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_datasource_id ON action_runs (datasource_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_recommendation_id ON action_runs (recommendation_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_approval_id ON action_runs (approval_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_skill_execution_id ON action_runs (skill_execution_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_verification_skill_execution_id ON action_runs (verification_skill_execution_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_runs_status ON action_runs (status)"))

        logger.info("Migration complete: created action_runs table")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
