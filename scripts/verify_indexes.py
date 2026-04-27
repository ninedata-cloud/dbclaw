"""验证模型中的索引定义是否覆盖了迁移脚本中的索引"""
import asyncio
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_engine, Base
import backend.models  # noqa: F401


async def get_model_indexes():
    """从模型定义中提取索引和约束"""
    indexes = {}
    for table_name, table in Base.metadata.tables.items():
        indexes[table_name] = []
        # 提取索引
        for index in table.indexes:
            columns = [col.name for col in index.columns]
            indexes[table_name].append({
                'name': index.name,
                'columns': columns,
                'unique': index.unique
            })
        # 提取唯一约束
        for constraint in table.constraints:
            if hasattr(constraint, 'name') and constraint.name and 'unique' in constraint.__class__.__name__.lower():
                columns = [col.name for col in constraint.columns]
                indexes[table_name].append({
                    'name': constraint.name,
                    'columns': columns,
                    'unique': True
                })
    return indexes


async def get_migration_indexes():
    """从迁移脚本中提取的关键索引（手动整理）"""
    return {
        'alert_message': [
            {'name': 'idx_alert_message_event_created_at', 'columns': ['event_id', 'created_at']},
            {'name': 'idx_alert_message_status_created_at_id', 'columns': ['status', 'created_at', 'id']},
        ],
        'datasource_metric': [
            {'name': 'idx_datasource_metric_composite', 'columns': ['datasource_id', 'metric_type', 'collected_at']},
            {'name': 'ix_datasource_metric_composite_asc', 'columns': ['datasource_id', 'metric_type', 'collected_at']},
        ],
        'diagnosis_conclusion': [
            {'name': 'idx_diagnosis_conclusion_session_updated_at_id', 'columns': ['session_id', 'updated_at', 'id']},
        ],
        'diagnosis_event': [
            {'name': 'idx_diagnosis_event_session_run_sequence_id', 'columns': ['session_id', 'run_id', 'sequence_no', 'id']},
        ],
        'host_metric': [
            {'name': 'idx_host_metric_host_id_collected_at', 'columns': ['host_id', 'collected_at']},
        ],
        'report': [
            {'name': 'idx_report_datasource_id', 'columns': ['datasource_id']},
            {'name': 'idx_report_datasource_created_at', 'columns': ['datasource_id', 'created_at']},
            {'name': 'idx_report_status', 'columns': ['status']},
            {'name': 'idx_report_trigger_type', 'columns': ['trigger_type']},
            {'name': 'idx_report_created_at', 'columns': ['created_at']},
            {'name': 'idx_report_composite', 'columns': ['datasource_id', 'status', 'trigger_type', 'created_at']},
        ],
        'doc_category': [
            {'name': 'idx_doc_category_parent_sort', 'columns': ['parent_id', 'sort_order']},
        ],
        'doc_document': [
            {'name': 'idx_doc_document_category_active_sort', 'columns': ['category_id', 'is_active', 'is_deleted', 'sort_order']},
        ],
        'skill_execution': [
            {'name': 'idx_skill_executions_skill_id_created_at', 'columns': ['skill_id', 'created_at']},
        ],
        'skill_rating': [
            {'name': 'uq_skill_rating_skill_user', 'columns': ['skill_id', 'user_id']},
        ],
        'chat_channel_binding': [
            {'name': 'uq_chat_channel_binding_channel_chat_user', 'columns': ['channel_type', 'external_chat_id', 'external_user_id']},
        ],
    }


async def main():
    model_indexes = await get_model_indexes()
    migration_indexes = await get_migration_indexes()

    print("=" * 80)
    print("索引覆盖验证报告")
    print("=" * 80)

    all_covered = True

    for table_name, expected_indexes in migration_indexes.items():
        print(f"\n## {table_name}")

        if table_name not in model_indexes:
            print(f"  ❌ 表不存在于模型定义中")
            all_covered = False
            continue

        model_idx_names = {idx['name'] for idx in model_indexes[table_name]}

        for expected_idx in expected_indexes:
            idx_name = expected_idx['name']
            if idx_name in model_idx_names:
                print(f"  ✅ {idx_name}")
            else:
                print(f"  ❌ {idx_name} - 缺失")
                all_covered = False

    print("\n" + "=" * 80)
    if all_covered:
        print("✅ 所有关键索引已覆盖")
    else:
        print("❌ 部分索引缺失，需要补充")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
