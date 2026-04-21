"""
Migration: Add DingTalk Webhook fields to alert_subscription

Adds dingtalk_webhook_url and dingtalk_secret columns.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import engine


async def run_migration():
    async with engine.begin() as conn:
        print("Adding DingTalk fields to alert_subscription...")

        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'alert_subscription'
            AND column_name IN ('dingtalk_webhook_url', 'dingtalk_secret')
        """))
        existing = {row[0] for row in result.fetchall()}

        if 'dingtalk_webhook_url' not in existing:
            await conn.execute(text("""
                ALTER TABLE alert_subscription
                ADD COLUMN dingtalk_webhook_url VARCHAR(500)
            """))
            print("Added dingtalk_webhook_url column.")

        if 'dingtalk_secret' not in existing:
            await conn.execute(text("""
                ALTER TABLE alert_subscription
                ADD COLUMN dingtalk_secret VARCHAR(200)
            """))
            print("Added dingtalk_secret column.")

        print("DingTalk migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
