import asyncio
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        user_columns_result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'user' "
            "AND column_name IN ('session_version', 'password_changed_at')"
        ))
        user_columns = {row[0] for row in user_columns_result.fetchall()}

        if 'session_version' not in user_columns:
            logger.info("Adding session_version column to user table...")
            await conn.execute(text("ALTER TABLE user ADD COLUMN session_version INTEGER DEFAULT 1"))
            await conn.execute(text("UPDATE user SET session_version = 1 WHERE session_version IS NULL"))
            await conn.execute(text("ALTER TABLE user ALTER COLUMN session_version SET NOT NULL"))

        if 'password_changed_at' not in user_columns:
            logger.info("Adding password_changed_at column to user table...")
            await conn.execute(text("ALTER TABLE user ADD COLUMN password_changed_at TIMESTAMP NULL"))

        session_table_result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'user_session')"
        ))
        session_table_exists = bool(session_table_result.scalar())
        if not session_table_exists:
            logger.info("Creating user_session table...")
            await conn.execute(text("""
                CREATE TABLE user_session (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id_hash VARCHAR(128) NOT NULL UNIQUE,
                    session_version INTEGER NOT NULL DEFAULT 1,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMP NOT NULL,
                    revoked_at TIMESTAMP NULL,
                    revoked_reason VARCHAR(100) NULL,
                    ip_address VARCHAR(64) NULL,
                    user_agent VARCHAR(500) NULL
                )
            """))
            await conn.execute(text("CREATE INDEX ix_user_session_user_id ON user_session(user_id)"))
            await conn.execute(text("CREATE INDEX ix_user_session_status ON user_session(status)"))
            await conn.execute(text("CREATE INDEX ix_user_session_expires_at ON user_session(expires_at)"))

        session_columns_result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'user_session' AND column_name IN ('session_version')"
        ))
        session_columns = {row[0] for row in session_columns_result.fetchall()}
        if session_table_exists and 'session_version' not in session_columns:
            logger.info("Adding session_version column to user_session table...")
            await conn.execute(text("ALTER TABLE user_session ADD COLUMN session_version INTEGER DEFAULT 1"))
            await conn.execute(text("UPDATE user_session SET session_version = 1 WHERE session_version IS NULL"))
            await conn.execute(text("ALTER TABLE user_session ALTER COLUMN session_version SET NOT NULL"))

        chat_columns_result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'diagnostic_session' AND column_name IN ('user_id')"
        ))
        chat_columns = {row[0] for row in chat_columns_result.fetchall()}
        if 'user_id' not in chat_columns:
            logger.info("Adding user_id column to diagnostic_session table...")
            await conn.execute(text("ALTER TABLE diagnostic_session ADD COLUMN user_id INTEGER NULL"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_diagnostic_session_user_id ON diagnostic_session(user_id)"))

        logger.info("Migration complete: added session security tables and columns")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
