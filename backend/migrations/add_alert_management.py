"""
Migration: Add Alert Management Module

Creates tables for alert messages, subscriptions, and delivery logs.
Adds email and phone fields to user table.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import engine, async_session


async def run_migration():
    """Run the alert management migration"""
    async with engine.begin() as conn:
        print("Starting alert management migration...")

        # Create alert_message table
        print("Creating alert_message table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_message (
                id SERIAL PRIMARY KEY,
                datasource_id INTEGER NOT NULL,
                alert_type VARCHAR(50) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                metric_name VARCHAR(100),
                metric_value REAL,
                threshold_value REAL,
                trigger_reason TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                acknowledged_by INTEGER,
                acknowledged_at TIMESTAMP,
                resolved_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datasource_id) REFERENCES datasource(id),
                FOREIGN KEY (acknowledged_by) REFERENCES user(id)
            )
        """))

        # Create indexes for alert_message
        print("Creating indexes for alert_message...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_message_datasource_id
            ON alert_message(datasource_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_message_alert_type
            ON alert_message(alert_type)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_message_severity
            ON alert_message(severity)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_message_status
            ON alert_message(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_message_created_at
            ON alert_message(created_at)
        """))

        # Create alert_subscription table
        print("Creating alert_subscription table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_subscription (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                datasource_ids TEXT NOT NULL DEFAULT '[]',
                severity_levels TEXT NOT NULL DEFAULT '[]',
                time_ranges TEXT NOT NULL DEFAULT '[]',
                channels TEXT NOT NULL DEFAULT '[]',
                webhook_url VARCHAR(500),
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                aggregation_script TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        """))

        # Create indexes for alert_subscription
        print("Creating indexes for alert_subscription...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_subscription_user_id
            ON alert_subscription(user_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_subscription_enabled
            ON alert_subscription(enabled)
        """))

        # Create alert_delivery_log table
        print("Creating alert_delivery_log table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_delivery_log (
                id SERIAL PRIMARY KEY,
                alert_id INTEGER NOT NULL,
                subscription_id INTEGER NOT NULL,
                channel VARCHAR(20) NOT NULL,
                recipient VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error_message TEXT,
                sent_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (alert_id) REFERENCES alert_message(id),
                FOREIGN KEY (subscription_id) REFERENCES alert_subscription(id)
            )
        """))

        # Create indexes for alert_delivery_log
        print("Creating indexes for alert_delivery_log...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_log_alert_id
            ON alert_delivery_log(alert_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_log_subscription_id
            ON alert_delivery_log(subscription_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_log_status
            ON alert_delivery_log(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_log_created_at
            ON alert_delivery_log(created_at)
        """))

        # Check if email and phone columns exist in user table
        print("Checking user table structure...")
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'user' AND column_name IN ('email', 'phone')
        """))
        existing_columns = [row[0] for row in result.fetchall()]

        # Add email column if not exists
        if 'email' not in existing_columns:
            print("Adding email column to user table...")
            await conn.execute(text("""
                ALTER TABLE user ADD COLUMN email VARCHAR(255)
            """))

        # Add phone column if not exists
        if 'phone' not in existing_columns:
            print("Adding phone column to user table...")
            await conn.execute(text("""
                ALTER TABLE user ADD COLUMN phone VARCHAR(50)
            """))

        print("Alert management migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
