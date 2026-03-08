"""
Migration: Add CASCADE DELETE to datasource foreign keys
添加级联删除约束到数据源外键
"""
import sqlite3
import os


def migrate():
    """Add CASCADE DELETE constraints to datasource foreign keys"""
    db_path = os.path.join(os.path.dirname(__file__), '../../data/smartdba.db')

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # SQLite doesn't support ALTER FOREIGN KEY directly
        # We need to recreate tables with CASCADE DELETE

        print("Starting migration: add_cascade_delete")

        # 1. metric_baselines
        print("Migrating metric_baselines...")
        cursor.execute("PRAGMA foreign_keys=off")

        cursor.execute("""
            CREATE TABLE metric_baselines_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                metric_name VARCHAR(100) NOT NULL,
                time_window VARCHAR(20),
                p50 FLOAT,
                p95 FLOAT,
                p99 FLOAT,
                mean FLOAT,
                stddev FLOAT,
                upper_threshold FLOAT,
                lower_threshold FLOAT,
                sample_count INTEGER,
                last_updated DATETIME,
                confidence_score FLOAT,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                UNIQUE (datasource_id, metric_name, time_window)
            )
        """)

        cursor.execute("""
            INSERT INTO metric_baselines_new
            SELECT * FROM metric_baselines
        """)

        cursor.execute("DROP TABLE metric_baselines")
        cursor.execute("ALTER TABLE metric_baselines_new RENAME TO metric_baselines")

        # 2. datasource_importance
        print("Migrating datasource_importance...")
        cursor.execute("""
            CREATE TABLE datasource_importance_new (
                datasource_id INTEGER PRIMARY KEY,
                importance_score FLOAT,
                importance_tier VARCHAR(20),
                connection_frequency FLOAT DEFAULT 0.0,
                query_volume FLOAT DEFAULT 0.0,
                business_hours_activity FLOAT DEFAULT 0.0,
                data_change_rate FLOAT DEFAULT 0.0,
                downstream_dependencies INTEGER DEFAULT 0,
                historical_incidents INTEGER DEFAULT 0,
                user_interaction_count INTEGER DEFAULT 0,
                collection_interval INTEGER DEFAULT 15,
                anomaly_detection_mode VARCHAR(20) DEFAULT 'batch',
                auto_fix_enabled BOOLEAN DEFAULT 0,
                last_recalculated DATETIME,
                score_history JSON,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            INSERT INTO datasource_importance_new
            SELECT * FROM datasource_importance
        """)

        cursor.execute("DROP TABLE datasource_importance")
        cursor.execute("ALTER TABLE datasource_importance_new RENAME TO datasource_importance")

        # 3. anomalies
        print("Migrating anomalies...")
        cursor.execute("""
            CREATE TABLE anomalies_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                detected_at DATETIME,
                anomaly_type VARCHAR(50),
                affected_metrics JSON,
                severity VARCHAR(20),
                confidence FLOAT,
                baseline_value FLOAT,
                current_value FLOAT,
                deviation_percent FLOAT,
                context_snapshot JSON,
                ai_diagnosis TEXT,
                root_cause TEXT,
                recommended_actions JSON,
                status VARCHAR(20) DEFAULT 'detected',
                resolved_at DATETIME,
                resolution_actions JSON,
                was_auto_fixed BOOLEAN DEFAULT 0,
                created_case BOOLEAN DEFAULT 0,
                case_id INTEGER,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                FOREIGN KEY (case_id) REFERENCES diagnostic_cases(id)
            )
        """)

        cursor.execute("""
            INSERT INTO anomalies_new
            SELECT * FROM anomalies
        """)

        cursor.execute("DROP TABLE anomalies")
        cursor.execute("ALTER TABLE anomalies_new RENAME TO anomalies")

        # 4. diagnostic_cases
        print("Migrating diagnostic_cases...")
        cursor.execute("""
            CREATE TABLE diagnostic_cases_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                created_at DATETIME,
                symptoms JSON,
                symptom_embedding BLOB,
                initial_metrics JSON,
                root_cause TEXT,
                diagnosis_steps JSON,
                diagnostic_conversation_id INTEGER,
                actions_taken JSON,
                effectiveness FLOAT,
                resolution_time INTEGER,
                reusable_solution BOOLEAN DEFAULT 0,
                solution_template_id INTEGER,
                times_reused INTEGER DEFAULT 0,
                tags JSON,
                user_rating INTEGER,
                user_feedback TEXT,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                FOREIGN KEY (diagnostic_conversation_id) REFERENCES diagnostic_sessions(id)
            )
        """)

        cursor.execute("""
            INSERT INTO diagnostic_cases_new
            SELECT * FROM diagnostic_cases
        """)

        cursor.execute("DROP TABLE diagnostic_cases")
        cursor.execute("ALTER TABLE diagnostic_cases_new RENAME TO diagnostic_cases")

        # 5. guardian_alerts
        print("Migrating guardian_alerts...")
        cursor.execute("""
            CREATE TABLE guardian_alerts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                anomaly_id INTEGER,
                rule_id INTEGER,
                created_at DATETIME,
                severity VARCHAR(20),
                title VARCHAR(200),
                message TEXT,
                channels JSON,
                sent_at DATETIME,
                status VARCHAR(20) DEFAULT 'pending',
                acknowledged_at DATETIME,
                user_action VARCHAR(50),
                created_chat_session BOOLEAN DEFAULT 0,
                chat_session_id INTEGER,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                FOREIGN KEY (anomaly_id) REFERENCES anomalies(id),
                FOREIGN KEY (rule_id) REFERENCES guardian_rules(id),
                FOREIGN KEY (chat_session_id) REFERENCES diagnostic_sessions(id)
            )
        """)

        cursor.execute("""
            INSERT INTO guardian_alerts_new
            SELECT * FROM guardian_alerts
        """)

        cursor.execute("DROP TABLE guardian_alerts")
        cursor.execute("ALTER TABLE guardian_alerts_new RENAME TO guardian_alerts")

        # 6. rule_executions
        print("Migrating rule_executions...")
        cursor.execute("""
            CREATE TABLE rule_executions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL,
                datasource_id INTEGER NOT NULL,
                executed_at DATETIME,
                trigger_context JSON,
                conditions_met JSON,
                actions_executed JSON,
                required_approval BOOLEAN DEFAULT 0,
                approved_by INTEGER,
                success BOOLEAN,
                error_message TEXT,
                execution_time_ms INTEGER,
                was_helpful BOOLEAN,
                user_feedback TEXT,
                FOREIGN KEY (rule_id) REFERENCES guardian_rules(id),
                FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE,
                FOREIGN KEY (approved_by) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            INSERT INTO rule_executions_new
            SELECT * FROM rule_executions
        """)

        cursor.execute("DROP TABLE rule_executions")
        cursor.execute("ALTER TABLE rule_executions_new RENAME TO rule_executions")

        cursor.execute("PRAGMA foreign_keys=on")

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
