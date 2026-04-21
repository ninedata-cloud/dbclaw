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
        print("Creating inspection_config table...")
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS inspection_config (
                id SERIAL PRIMARY KEY,
                datasource_id INTEGER UNIQUE NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                schedule_interval INTEGER NOT NULL DEFAULT 86400,
                use_ai_analysis BOOLEAN NOT NULL DEFAULT TRUE,
                ai_model_id INTEGER,
                kb_ids TEXT NOT NULL DEFAULT '[]',
                threshold_rules TEXT NOT NULL DEFAULT '{}',
                anomaly_check_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                anomaly_diagnosis_interval INTEGER NOT NULL DEFAULT 600,
                last_scheduled_at TIMESTAMP,
                next_scheduled_at TIMESTAMP,
                last_anomaly_diagnosis_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datasource_id) REFERENCES datasource(id)
            )
        """))

        print("Creating inspection_trigger table...")
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS inspection_trigger (
                id SERIAL PRIMARY KEY,
                datasource_id INTEGER NOT NULL,
                trigger_type VARCHAR(20) NOT NULL,
                trigger_reason VARCHAR(500),
                datasource_metric TEXT,
                triggered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN NOT NULL DEFAULT FALSE,
                report_id INTEGER,
                FOREIGN KEY (datasource_id) REFERENCES datasource(id),
                FOREIGN KEY (report_id) REFERENCES report(id)
            )
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_triggers_datasource ON inspection_trigger(datasource_id)"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_triggers_time ON inspection_trigger(triggered_at)"))

        # 2. Add trigger columns to report table
        print("Adding trigger columns to report table...")
        result = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'report' AND column_name IN ('trigger_type', 'trigger_id', 'trigger_reason')
        """))
        existing_columns = {row[0] for row in result.fetchall()}

        if 'trigger_type' not in existing_columns:
            await db.execute(text("ALTER TABLE report ADD COLUMN trigger_type VARCHAR(20)"))
        if 'trigger_id' not in existing_columns:
            await db.execute(text("ALTER TABLE report ADD COLUMN trigger_id INTEGER REFERENCES inspection_trigger(id)"))
        if 'trigger_reason' not in existing_columns:
            await db.execute(text("ALTER TABLE report ADD COLUMN trigger_reason VARCHAR(500)"))
        print("Trigger columns added")

        # 3. Migrate scheduled_report_configs to inspection_config
        print("Migrating scheduled report configs...")
        result = await db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'scheduled_report_configs'
        """))
        if result.fetchone():
            # Check what columns exist
            result = await db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'scheduled_report_configs'
            """))
            columns = {row[0] for row in result.fetchall()}

            if 'interval_seconds' in columns:
                await db.execute(text("""
                    INSERT INTO inspection_config (datasource_id, enabled, schedule_interval, use_ai_analysis, ai_model_id, kb_ids, next_scheduled_at)
                    SELECT datasource_id, enabled, interval_seconds, use_ai_analysis, ai_model_id,
                           COALESCE(kb_ids, '[]'), next_run_at
                    FROM scheduled_report_configs
                """))
                print("Migrated scheduled report configs")
            else:
                print("Skipping migration - scheduled_report_configs has different schema")
        else:
            print("No scheduled_report_configs table found - skipping migration")

        # 4. Mark existing scheduled report
        print("Marking existing scheduled report...")
        await db.execute(text("""
            UPDATE report
            SET trigger_type = 'scheduled'
            WHERE is_scheduled = TRUE
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
            result = await db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = :tname
            """), {"tname": table})
            if result.fetchone():
                await db.execute(text(f"DROP TABLE {table}"))
                print(f"Dropped table: {table}")

        await db.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(migrate())
