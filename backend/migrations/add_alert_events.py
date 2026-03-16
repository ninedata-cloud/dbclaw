"""
Migration: Add alert_events table and event_id to alert_messages

This migration creates the alert aggregation system:
1. Creates alert_events table for aggregated alert events
2. Adds event_id column to alert_messages table
3. Processes existing alerts into events (retroactive aggregation)
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from typing import Dict

import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path.parent))

from backend.config import DATABASE_URL
from backend.models.alert_message import AlertMessage
from sqlalchemy import select


async def create_alert_events_table(session: AsyncSession):
    """Create alert_events table with indexes"""
    print("Creating alert_events table...")

    await session.execute(text("""
        CREATE TABLE IF NOT EXISTS alert_events (
            id SERIAL PRIMARY KEY,
            datasource_id INTEGER NOT NULL,
            aggregation_key VARCHAR(255) NOT NULL,
            aggregation_type VARCHAR(50) NOT NULL,

            first_alert_id INTEGER NOT NULL,
            latest_alert_id INTEGER NOT NULL,
            alert_count INTEGER NOT NULL DEFAULT 1,

            event_start_time TIMESTAMP NOT NULL,
            event_end_time TIMESTAMP NOT NULL,
            last_updated TIMESTAMP NOT NULL,

            status VARCHAR(20) NOT NULL,
            severity VARCHAR(20) NOT NULL,

            title VARCHAR(255) NOT NULL,
            alert_type VARCHAR(50),
            metric_name VARCHAR(100),

            FOREIGN KEY (datasource_id) REFERENCES datasources(id),
            FOREIGN KEY (first_alert_id) REFERENCES alert_messages(id),
            FOREIGN KEY (latest_alert_id) REFERENCES alert_messages(id)
        )
    """))

    print("Creating indexes on alert_events...")
    await session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_datasource_id ON alert_events(datasource_id)"
    ))
    await session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_aggregation_key ON alert_events(aggregation_key)"
    ))
    await session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_status ON alert_events(status)"
    ))
    await session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_event_start_time ON alert_events(event_start_time)"
    ))
    await session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_event_end_time ON alert_events(event_end_time)"
    ))

    await session.commit()
    print("alert_events table created")


async def add_event_id_to_alert_messages(session: AsyncSession):
    """Add event_id column to alert_messages table"""
    print("Adding event_id column to alert_messages...")

    # Check if column already exists
    result = await session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'alert_messages' AND column_name = 'event_id'
    """))
    if result.fetchone():
        print("event_id column already exists")
        return

    await session.execute(text(
        "ALTER TABLE alert_messages ADD COLUMN event_id INTEGER"
    ))
    await session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_alert_messages_event_id ON alert_messages(event_id)"
    ))
    await session.commit()
    print("event_id column added")


async def aggregate_existing_alerts(session: AsyncSession, time_window_minutes: int = 5):
    """Process existing alerts into events (retroactive aggregation)"""
    print(f"Aggregating existing alerts (time window: {time_window_minutes} minutes)...")

    result = await session.execute(
        select(AlertMessage)
        .where(AlertMessage.event_id.is_(None))
        .order_by(AlertMessage.created_at)
    )
    alerts = result.scalars().all()

    if not alerts:
        print("No alerts to aggregate")
        return

    print(f"Found {len(alerts)} alerts to process")

    events: Dict[str, Dict] = {}
    time_window = timedelta(minutes=time_window_minutes)

    for alert in alerts:
        if alert.metric_name:
            aggregation_key = f"{alert.datasource_id}:{alert.metric_name}"
            aggregation_type = "by_metric_name"
        else:
            aggregation_key = f"{alert.datasource_id}:{alert.alert_type}"
            aggregation_type = "by_alert_type"

        matching_event = None
        if aggregation_key in events:
            event_data = events[aggregation_key]
            time_gap = alert.created_at - event_data['event_end_time']
            if time_gap <= time_window:
                matching_event = event_data

        if matching_event:
            matching_event['latest_alert_id'] = alert.id
            matching_event['alert_count'] += 1
            matching_event['event_end_time'] = alert.created_at
            matching_event['last_updated'] = datetime.utcnow()
            matching_event['status'] = alert.status

            severity_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
            if severity_order.get(alert.severity, 0) > severity_order.get(matching_event['severity'], 0):
                matching_event['severity'] = alert.severity

            matching_event['alert_ids'].append(alert.id)
        else:
            events[aggregation_key] = {
                'datasource_id': alert.datasource_id,
                'aggregation_key': aggregation_key,
                'aggregation_type': aggregation_type,
                'first_alert_id': alert.id,
                'latest_alert_id': alert.id,
                'alert_count': 1,
                'event_start_time': alert.created_at,
                'event_end_time': alert.created_at,
                'last_updated': datetime.utcnow(),
                'status': alert.status,
                'severity': alert.severity,
                'title': alert.title,
                'alert_type': alert.alert_type,
                'metric_name': alert.metric_name,
                'alert_ids': [alert.id]
            }

    print(f"Creating {len(events)} events...")
    for event_data in events.values():
        alert_ids = event_data.pop('alert_ids')

        result = await session.execute(text("""
            INSERT INTO alert_events (
                datasource_id, aggregation_key, aggregation_type,
                first_alert_id, latest_alert_id, alert_count,
                event_start_time, event_end_time, last_updated,
                status, severity, title, alert_type, metric_name
            ) VALUES (
                :datasource_id, :aggregation_key, :aggregation_type,
                :first_alert_id, :latest_alert_id, :alert_count,
                :event_start_time, :event_end_time, :last_updated,
                :status, :severity, :title, :alert_type, :metric_name
            ) RETURNING id
        """), event_data)

        event_id = result.scalar()

        for alert_id in alert_ids:
            await session.execute(
                text("UPDATE alert_messages SET event_id = :event_id WHERE id = :alert_id"),
                {'event_id': event_id, 'alert_id': alert_id}
            )

    await session.commit()
    print(f"Created {len(events)} events from {len(alerts)} alerts")


async def main():
    """Run migration"""
    print("=" * 60)
    print("Alert Events Migration")
    print("=" * 60)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_factory() as session:
        try:
            await create_alert_events_table(session)
            await add_event_id_to_alert_messages(session)
            await aggregate_existing_alerts(session)

            print("=" * 60)
            print("Migration completed successfully")
            print("=" * 60)

        except Exception as e:
            print(f"Migration failed: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
