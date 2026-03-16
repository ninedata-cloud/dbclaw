"""Add system_configs table and initialize default configurations"""
import asyncio
from sqlalchemy import text
from backend.database import async_session


async def migrate():
    async with async_session() as db:
        # Check if table exists
        result = await db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'system_configs'
        """))
        if result.scalar_one_or_none():
            print("Table system_configs already exists")
            return

        # Create table
        await db.execute(text("""
            CREATE TABLE system_configs (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) UNIQUE NOT NULL,
                value TEXT,
                value_type VARCHAR(20) NOT NULL,
                description TEXT,
                category VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes
        await db.execute(text(
            "CREATE INDEX idx_system_configs_key ON system_configs(key)"
        ))
        await db.execute(text(
            "CREATE INDEX idx_system_configs_category ON system_configs(category)"
        ))

        # Insert initial configurations
        await db.execute(text("""
            INSERT INTO system_configs (key, value, value_type, description, category)
            VALUES
            ('bocha_api_key', 'sk-66d203942a6c404b89eff2adb494febc', 'string', 'Bocha AI Web Search API Key', 'external_api'),
            ('bocha_api_url', 'https://api.bochaai.com/v1/web-search', 'string', 'Bocha AI Web Search API URL', 'external_api')
        """))

        await db.commit()
        print("Successfully created system_configs table and initialized default configurations")


if __name__ == "__main__":
    asyncio.run(migrate())
