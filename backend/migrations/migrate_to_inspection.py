"""Migration: Replace Guardian and Scheduled Reports with Inspection System"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.database import async_session


async def migrate():
    """Migrate from old Guardian/ScheduledReport system to new Inspection system"""
    async with async_session() as db:
        print("Starting migration to Inspection system...")

        # 1. Create new tables
        print("Creating inspection_configs table...")
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS inspection_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER UNIQUE NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                schedule_interval INTEGER NOT NULL DEFAULT 86400,
                use_ai_analysis BOOLEAN NOT NULL DEFAULT 1,
                ai_model_id INTEGER,
                kb_ids TEXT NOT NULL DEFAULT '[]',
                threshold_rules TEXT NOT NULL DEFAULT '{}',
                anomaly_check_enabled BOOLEAN NOT NULL DEFAULT 1,
                anomaly_diagnosis_interval INTEGER NOT NULL DEFAULT 600,
                last_scheduled_at TIMESTAMP,
                next_scheduled_at TIMESTAMP,
                last_anomaly_diagnosis_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id)
            )
        """))

        print("Creating inspection_triggers table...")
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS inspection_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                trigger_type VARCHAR(20) NOT NULL,
                trigger_reason VARCHAR(500),
                metric_snapshot TEXT,
                triggered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN NOT NULL DEFAULT 0,
                report_id INTEGER,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id),
                FOREIGN KEY (report_id) REFERENCES reports(id)
            )
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_triggers_datasource ON inspection_triggers(datasource_id)"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_triggers_time ON inspection_triggers(triggered_at)"))

        # 2. Add trigger columns to reports table
        print("Adding trigger columns to reports table...")
        result = await db.execute(text("PRAGMA table_info(reports)"))
        existing_columns = {row[1] for row in result.fetchall()}

        if 'trigger_type' not in existing_columns:
            await db.execute(text("ALTER TABLE reports ADD COLUMN trigger_type VARCHAR(20)"))
        if 'trigger_id' not in existing_columns:
            await db.execute(text("ALTER TABLE reports ADD COLUMN trigger_id INTEGER REFERENCES inspection_triggers(id)"))
        if 'trigger_reason' not in existing_columns:
            await db.execute(text("ALTER TABLE reports ADD COLUMN trigger_reason VARCHAR(500)"))
        print("Trigger columns added")

        # 3. Migrate scheduled_report_configs to inspection_configs
        print("Migrating scheduled report configs...")
        result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_report_configs'"))
        if result.fetchone():
            # Check what columns exist
            result = await db.execute(text("PRAGMA table_info(scheduled_report_configs)"))
            columns = {row[1] for row in result.fetchall()}

            if 'interval_seconds' in columns:
                await db.execute(text("""
                    INSERT INTO inspection_configs (datasource_id, enabled, schedule_interval, use_ai_analysis, ai_model_id, kb_ids, next_scheduled_at)
                    SELECT datasource_id, enabled, interval_seconds, use_ai_analysis, ai_model_id,
                           COALESCE(kb_ids, '[]'), next_run_at
                    FROM scheduled_report_configs
                """))
                print("Migrated scheduled report configs")
            else:
                print("Skipping migration - scheduled_report_configs has different schema")
        else:
            print("No scheduled_report_configs table found - skipping migration")

        # 4. Mark existing scheduled reports
        print("Marking existing scheduled reports...")
        await db.execute(text("""
            UPDATE reports
            SET trigger_type = 'scheduled'
            WHERE is_scheduled = 1
        """))

        # 5. Drop old tables
        print("Dropping old Guardian tables...")
        old_tables = [
            "metric_baselines",
            "datasource_importance",
            "anomalies",
            "guardian_alerts",
            "scheduled_report_configs",
            "scheduled_report_history"
        ]

        for table in old_tables:
            result = await db.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"))
            if result.fetchone():
                await db.execute(text(f"DROP TABLE {table}"))
                print(f"Dropped table: {table}")

        await db.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(migrate())
