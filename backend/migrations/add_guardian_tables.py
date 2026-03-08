"""
Database Migration: Add AI Guardian Tables
添加 AI 守护系统表
"""
import asyncio
from sqlalchemy import text
from backend.database import get_db


async def upgrade():
    """添加 AI 守护系统表"""

    async for db in get_db():
        # 1. 创建 metric_baselines 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS metric_baselines (
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
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence_score FLOAT,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id),
                UNIQUE(datasource_id, metric_name, time_window)
            )
        """))

        # 2. 创建 datasource_importance 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS datasource_importance (
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
                auto_fix_enabled BOOLEAN DEFAULT FALSE,
                last_recalculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                score_history TEXT,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id)
            )
        """))

        # 3. 创建 anomalies 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                anomaly_type VARCHAR(50),
                affected_metrics TEXT,
                severity VARCHAR(20),
                confidence FLOAT,
                baseline_value FLOAT,
                current_value FLOAT,
                deviation_percent FLOAT,
                context_snapshot TEXT,
                ai_diagnosis TEXT,
                root_cause TEXT,
                recommended_actions TEXT,
                status VARCHAR(20) DEFAULT 'detected',
                resolved_at TIMESTAMP,
                resolution_actions TEXT,
                was_auto_fixed BOOLEAN DEFAULT FALSE,
                created_case BOOLEAN DEFAULT FALSE,
                case_id INTEGER,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id)
            )
        """))

        # 4. 创建 guardian_rules 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS guardian_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200),
                description_nl TEXT,
                rule_embedding BLOB,
                conditions TEXT,
                actions TEXT,
                scope TEXT,
                effectiveness_score FLOAT DEFAULT 0.5,
                false_positive_rate FLOAT DEFAULT 0.0,
                execution_count INTEGER DEFAULT 0,
                last_triggered TIMESTAMP,
                created_by_dialogue BOOLEAN DEFAULT FALSE,
                training_conversation_id INTEGER,
                refinement_history TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (training_conversation_id) REFERENCES diagnostic_sessions(id)
            )
        """))

        # 5. 创建 rule_executions 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS rule_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL,
                datasource_id INTEGER NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trigger_context TEXT,
                conditions_met TEXT,
                actions_executed TEXT,
                required_approval BOOLEAN DEFAULT FALSE,
                approved_by INTEGER,
                success BOOLEAN,
                error_message TEXT,
                execution_time_ms INTEGER,
                was_helpful BOOLEAN,
                user_feedback TEXT,
                FOREIGN KEY (rule_id) REFERENCES guardian_rules(id),
                FOREIGN KEY (datasource_id) REFERENCES datasources(id),
                FOREIGN KEY (approved_by) REFERENCES users(id)
            )
        """))

        # 6. 创建 diagnostic_cases 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS diagnostic_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symptoms TEXT,
                symptom_embedding BLOB,
                initial_metrics TEXT,
                root_cause TEXT,
                diagnosis_steps TEXT,
                diagnostic_conversation_id INTEGER,
                actions_taken TEXT,
                effectiveness FLOAT,
                resolution_time INTEGER,
                reusable_solution BOOLEAN DEFAULT FALSE,
                solution_template_id INTEGER,
                times_reused INTEGER DEFAULT 0,
                tags TEXT,
                user_rating INTEGER,
                user_feedback TEXT,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id),
                FOREIGN KEY (diagnostic_conversation_id) REFERENCES diagnostic_sessions(id)
            )
        """))

        # 7. 创建 guardian_alerts 表
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS guardian_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datasource_id INTEGER NOT NULL,
                anomaly_id INTEGER,
                rule_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                severity VARCHAR(20),
                title VARCHAR(200),
                message TEXT,
                channels TEXT,
                sent_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending',
                acknowledged_at TIMESTAMP,
                user_action VARCHAR(50),
                created_chat_session BOOLEAN DEFAULT FALSE,
                chat_session_id INTEGER,
                FOREIGN KEY (datasource_id) REFERENCES datasources(id),
                FOREIGN KEY (anomaly_id) REFERENCES anomalies(id),
                FOREIGN KEY (rule_id) REFERENCES guardian_rules(id),
                FOREIGN KEY (chat_session_id) REFERENCES diagnostic_sessions(id)
            )
        """))

        # 8. 扩展 skills 表
        try:
            await db.execute(text("ALTER TABLE skills ADD COLUMN risk_level VARCHAR(20)"))
        except:
            pass  # Column already exists

        try:
            await db.execute(text("ALTER TABLE skills ADD COLUMN auto_executable BOOLEAN DEFAULT FALSE"))
        except:
            pass

        try:
            await db.execute(text("ALTER TABLE skills ADD COLUMN rollback_supported BOOLEAN DEFAULT FALSE"))
        except:
            pass

        await db.commit()
        print("✅ AI Guardian tables created successfully")
        break


async def downgrade():
    """回滚迁移"""
    async for db in get_db():
        await db.execute(text("DROP TABLE IF EXISTS guardian_alerts"))
        await db.execute(text("DROP TABLE IF EXISTS diagnostic_cases"))
        await db.execute(text("DROP TABLE IF EXISTS rule_executions"))
        await db.execute(text("DROP TABLE IF EXISTS guardian_rules"))
        await db.execute(text("DROP TABLE IF EXISTS anomalies"))
        await db.execute(text("DROP TABLE IF EXISTS datasource_importance"))
        await db.execute(text("DROP TABLE IF EXISTS metric_baselines"))

        await db.commit()
        print("✅ AI Guardian tables dropped successfully")
        break


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())
