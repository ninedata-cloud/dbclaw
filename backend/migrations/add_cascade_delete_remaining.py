"""
Migration: Add CASCADE DELETE to remaining datasource foreign keys
添加级联删除约束到剩余的数据源外键（metric_snapshots, reports, diagnostic_sessions）
"""
import sqlite3
import os


def migrate():
    """Add CASCADE DELETE constraints to remaining datasource foreign keys"""
    db_path = os.path.join(os.path.dirname(__file__), '../../data/smartdba.db')

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Starting migration: add_cascade_delete_remaining")
        cursor.execute("PRAGMA foreign_keys=off")

        # 1. metric_snapshots (has 9059 records)
        print("Migrating metric_snapshots...")
        cursor.execute("""
            CREATE TABLE metric_snapshots_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                metric_type VARCHAR(50) NOT NULL,
                data JSON NOT NULL,
                collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("CREATE INDEX idx_metric_snapshots_datasource ON metric_snapshots_new(datasource_id)")
        cursor.execute("CREATE INDEX idx_metric_snapshots_collected ON metric_snapshots_new(collected_at)")

        cursor.execute("""
            INSERT INTO metric_snapshots_new (id, datasource_id, metric_type, data, collected_at)
            SELECT id, datasource_id, metric_type, data, collected_at FROM metric_snapshots
        """)

        cursor.execute("DROP TABLE metric_snapshots")
        cursor.execute("ALTER TABLE metric_snapshots_new RENAME TO metric_snapshots")

        # 2. reports
        print("Migrating reports...")
        cursor.execute("""
            CREATE TABLE reports_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                report_type VARCHAR(50) DEFAULT 'comprehensive',
                status VARCHAR(20) DEFAULT 'generating',
                summary TEXT,
                content_md TEXT,
                content_html TEXT,
                findings JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                ai_analysis TEXT,
                ai_model_id INTEGER,
                kb_ids JSON,
                generation_method VARCHAR(20) DEFAULT 'rule-based',
                error_message TEXT,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            INSERT INTO reports_new
            SELECT * FROM reports
        """)

        cursor.execute("DROP TABLE reports")
        cursor.execute("ALTER TABLE reports_new RENAME TO reports")

        # 3. diagnostic_sessions
        print("Migrating diagnostic_sessions...")
        cursor.execute("""
            CREATE TABLE diagnostic_sessions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER,
                ai_model_id INTEGER,
                title VARCHAR(200) DEFAULT 'New Session',
                kb_ids JSON,
                disabled_tools JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                FOREIGN KEY (ai_model_id) REFERENCES ai_models(id)
            )
        """)

        cursor.execute("""
            INSERT INTO diagnostic_sessions_new
            SELECT * FROM diagnostic_sessions
        """)

        cursor.execute("DROP TABLE diagnostic_sessions")
        cursor.execute("ALTER TABLE diagnostic_sessions_new RENAME TO diagnostic_sessions")

        cursor.execute("PRAGMA foreign_keys=on")

        conn.commit()
        print("Migration completed successfully!")
        print("All datasource foreign keys now have CASCADE DELETE enabled.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
