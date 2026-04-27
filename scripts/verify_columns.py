#!/usr/bin/env python3
"""
验证迁移脚本中的列是否都在模型定义中
"""
import re
import os
from pathlib import Path

def extract_alter_table_columns(migration_dir):
    """从迁移脚本中提取 ALTER TABLE ADD COLUMN 语句"""
    columns_by_table = {}

    for file in Path(migration_dir).glob("*.py"):
        if file.name in ["__init__.py", "runner.py"]:
            continue

        content = file.read_text()

        # 匹配 ALTER TABLE ... ADD COLUMN 语句
        # 支持多种格式
        patterns = [
            r'ALTER TABLE\s+(\w+)\s+ADD COLUMN\s+(\w+)\s+([^,;]+)',
            r'ALTER TABLE\s+"?(\w+)"?\s+ADD COLUMN\s+"?(\w+)"?\s+([^,;]+)',
            r"op\.add_column\(['\"](\w+)['\"],\s*sa\.Column\(['\"](\w+)['\"],\s*([^)]+)\)",
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                table_name = match.group(1)
                column_name = match.group(2)
                column_type = match.group(3).strip()

                if table_name not in columns_by_table:
                    columns_by_table[table_name] = []

                columns_by_table[table_name].append({
                    'column': column_name,
                    'type': column_type,
                    'file': file.name
                })

    return columns_by_table

def extract_model_columns(models_dir):
    """从模型定义中提取列"""
    columns_by_table = {}

    for file in Path(models_dir).glob("*.py"):
        if file.name == "__init__.py":
            continue

        content = file.read_text()

        # 提取表名
        table_match = re.search(r'__tablename__\s*=\s*["\'](\w+)["\']', content)
        if not table_match:
            continue

        table_name = table_match.group(1)

        # 提取列定义 (简化版，只匹配 Column 定义)
        column_pattern = r'(\w+)\s*[:=]\s*(?:Mapped\[.*?\]\s*=\s*)?(?:mapped_column|Column)\('
        matches = re.finditer(column_pattern, content)

        columns = []
        for match in matches:
            column_name = match.group(1)
            # 排除一些非列的属性
            if column_name not in ['__tablename__', '__table_args__', '__mapper_args__']:
                columns.append(column_name)

        if columns:
            columns_by_table[table_name] = columns

    return columns_by_table

def main():
    project_root = Path(__file__).resolve().parent.parent
    migration_dir = project_root / "backend" / "migrations"
    models_dir = project_root / "backend" / "models"

    print("=== 提取迁移脚本中的 ALTER TABLE ADD COLUMN ===\n")
    migration_columns = extract_alter_table_columns(migration_dir)

    print("=== 提取模型定义中的列 ===\n")
    model_columns = extract_model_columns(models_dir)

    print("=== 对比结果 ===\n")

    missing_columns = {}

    for table_name, columns in sorted(migration_columns.items()):
        model_cols = model_columns.get(table_name, [])

        missing = []
        for col_info in columns:
            if col_info['column'] not in model_cols:
                missing.append(col_info)

        if missing:
            missing_columns[table_name] = missing

    if missing_columns:
        print("⚠️  发现以下表的列在模型中缺失:\n")
        for table_name, columns in sorted(missing_columns.items()):
            print(f"表: {table_name}")
            for col_info in columns:
                print(f"  - {col_info['column']} ({col_info['type']}) [来源: {col_info['file']}]")
            print()
    else:
        print("✅ 所有迁移脚本中的列都在模型定义中")

    # 统计信息
    print("\n=== 统计信息 ===")
    print(f"迁移脚本涉及的表数量: {len(migration_columns)}")
    print(f"模型定义的表数量: {len(model_columns)}")
    print(f"缺失列的表数量: {len(missing_columns)}")

    total_migration_cols = sum(len(cols) for cols in migration_columns.values())
    total_missing_cols = sum(len(cols) for cols in missing_columns.values())
    print(f"迁移脚本中的总列数: {total_migration_cols}")
    print(f"缺失的总列数: {total_missing_cols}")

if __name__ == "__main__":
    main()
