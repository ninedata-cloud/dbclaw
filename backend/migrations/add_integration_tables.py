"""
添加统一外部集成管理表：integrations、alert_channels、integration_execution_logs
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from backend.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """执行迁移"""
    engine = create_async_engine(settings.database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # 创建 integrations 表
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS integrations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    description VARCHAR(500),
                    integration_type VARCHAR(50) NOT NULL,
                    category VARCHAR(50) NOT NULL DEFAULT 'custom',
                    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
                    code TEXT NOT NULL,
                    config JSONB NOT NULL DEFAULT '{}',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    last_run_at TIMESTAMP,
                    last_error TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table: integrations")

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_integrations_type
                ON integrations(integration_type)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_integrations_enabled
                ON integrations(enabled)
            """))

            # 创建 alert_channels 表
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS alert_channels (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    description VARCHAR(500),
                    integration_id INTEGER NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
                    params JSONB NOT NULL DEFAULT '{}',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table: alert_channels")

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_alert_channels_integration_id
                ON alert_channels(integration_id)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_alert_channels_enabled
                ON alert_channels(enabled)
            """))

            # 创建 integration_execution_logs 表
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS integration_execution_logs (
                    id SERIAL PRIMARY KEY,
                    integration_id INTEGER NOT NULL,
                    channel_id INTEGER,
                    trigger_source VARCHAR(50) NOT NULL DEFAULT 'manual',
                    trigger_ref_id VARCHAR(100),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    execution_time_ms INTEGER,
                    result JSONB,
                    error_message TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table: integration_execution_logs")

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_integration_exec_logs_integration_id
                ON integration_execution_logs(integration_id)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_integration_exec_logs_created_at
                ON integration_execution_logs(created_at DESC)
            """))

            await session.commit()
            logger.info("Migration completed successfully")

        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
