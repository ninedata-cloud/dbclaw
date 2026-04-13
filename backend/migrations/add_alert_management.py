"""
Migration: Add Alert Management Module

Creates tables for alert messages, subscriptions, and delivery logs.
Adds email and phone fields to users table.
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

        # Create alert_messages table
        print("Creating alert_messages table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_messages (
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
                FOREIGN KEY (datasource_id) REFERENCES datasources(id),
                FOREIGN KEY (acknowledged_by) REFERENCES users(id)
            )
        """))

        # Create indexes for alert_messages
        print("Creating indexes for alert_messages...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_messages_datasource_id
            ON alert_messages(datasource_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_messages_alert_type
            ON alert_messages(alert_type)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_messages_severity
            ON alert_messages(severity)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_messages_status
            ON alert_messages(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_messages_created_at
            ON alert_messages(created_at)
        """))

        # Create alert_subscriptions table
        print("Creating alert_subscriptions table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_subscriptions (
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
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))

        # Create indexes for alert_subscriptions
        print("Creating indexes for alert_subscriptions...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_user_id
            ON alert_subscriptions(user_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_enabled
            ON alert_subscriptions(enabled)
        """))

        # Create alert_delivery_logs table
        print("Creating alert_delivery_logs table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_delivery_logs (
                id SERIAL PRIMARY KEY,
                alert_id INTEGER NOT NULL,
                subscription_id INTEGER NOT NULL,
                channel VARCHAR(20) NOT NULL,
                recipient VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error_message TEXT,
                sent_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (alert_id) REFERENCES alert_messages(id),
                FOREIGN KEY (subscription_id) REFERENCES alert_subscriptions(id)
            )
        """))

        # Create indexes for alert_delivery_logs
        print("Creating indexes for alert_delivery_logs...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_logs_alert_id
            ON alert_delivery_logs(alert_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_logs_subscription_id
            ON alert_delivery_logs(subscription_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_logs_status
            ON alert_delivery_logs(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_alert_delivery_logs_created_at
            ON alert_delivery_logs(created_at)
        """))

        # Check if email and phone columns exist in users table
        print("Checking users table structure...")
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name IN ('email', 'phone')
        """))
        existing_columns = [row[0] for row in result.fetchall()]

        # Add email column if not exists
        if 'email' not in existing_columns:
            print("Adding email column to users table...")
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN email VARCHAR(255)
            """))

        # Add phone column if not exists
        if 'phone' not in existing_columns:
            print("Adding phone column to users table...")
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN phone VARCHAR(50)
            """))

        print("Alert management migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
