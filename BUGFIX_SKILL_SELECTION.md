# Bug Fix: AI错误选择数据库类型的Skills

## 问题描述

在AI诊断过程中，PostgreSQL和SQL Server数据库总是会先尝试使用MySQL的skills，导致执行失败。

## 根本原因

在 `backend/agent/conversation_skills.py` 中，系统提示词只告诉AI当前使用的 `connection_id`，但**没有告诉AI这个连接的数据库类型**（mysql/postgresql/sqlserver/oracle）。

原代码（第88-90行）：
```python
system_msg = SYSTEM_PROMPT
if connection_id:
    system_msg += f"\n\nThe user is currently working with database connection ID: {connection_id}. Use this ID when calling tools unless they specify otherwise."
```

AI无法知道应该调用哪个数据库特定的skill，可能会：
- 随机尝试不同数据库的skills
- 默认尝试MySQL的skills（因为MySQL skills在列表中可能排在前面）
- 导致执行失败后再尝试正确的skill

## 解决方案

修改系统提示词，明确告知AI当前数据库的类型和应该使用的skill前缀：

```python
system_msg = SYSTEM_PROMPT
if connection_id and db:
    # Get connection info to determine database type
    from backend.models.connection import Connection
    from sqlalchemy import select
    result = await db.execute(select(Connection).filter(Connection.id == connection_id))
    conn = result.scalar_one_or_none()
    if conn:
        # Map db_type to skill prefix
        skill_prefix_map = {
            'mysql': 'mysql',
            'postgresql': 'pg',
            'sqlserver': 'mssql',
            'oracle': 'oracle'
        }
        skill_prefix = skill_prefix_map.get(conn.db_type, conn.db_type)

        system_msg += f"\n\nThe user is currently working with database connection ID: {connection_id} (Type: {conn.db_type.upper()}, Name: {conn.name}). Use this ID when calling tools unless they specify otherwise."
        system_msg += f"\n\nIMPORTANT: This is a {conn.db_type.upper()} database. You MUST use {skill_prefix}_* skills (e.g., {skill_prefix}_get_db_status, {skill_prefix}_get_slow_queries, {skill_prefix}_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type."
```

## 修改内容

### 文件：`backend/agent/conversation_skills.py`

1. **添加数据库类型查询**：在构建系统提示词时，查询数据库获取连接的类型信息
2. **添加skill前缀映射**：将数据库类型映射到实际的skill前缀
   - `mysql` → `mysql_*`
   - `postgresql` → `pg_*`
   - `sqlserver` → `mssql_*`
   - `oracle` → `oracle_*`
3. **增强系统提示词**：明确告知AI当前数据库类型和应该使用的skill前缀

## 效果示例

### PostgreSQL连接
```
The user is currently working with database connection ID: 2 (Type: POSTGRESQL, Name: 8.136.122.73-pg). Use this ID when calling tools unless they specify otherwise.

IMPORTANT: This is a POSTGRESQL database. You MUST use pg_* skills (e.g., pg_get_db_status, pg_get_slow_queries, pg_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type.
```

### SQL Server连接
```
The user is currently working with database connection ID: 4 (Type: SQLSERVER, Name: 8.136.122.73-sqlserver). Use this ID when calling tools unless they specify otherwise.

IMPORTANT: This is a SQLSERVER database. You MUST use mssql_* skills (e.g., mssql_get_db_status, mssql_get_slow_queries, mssql_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type.
```

## 测试

运行测试脚本验证修复：
```bash
python test_db_type_prompt.py
```

## 预期改进

1. **准确性提升**：AI将直接选择正确的数据库特定skills，不再尝试错误的类型
2. **性能提升**：减少失败重试，加快诊断响应速度
3. **用户体验**：减少错误信息，提供更流畅的诊断体验

## 相关文件

- `backend/agent/conversation_skills.py` - 主要修改文件
- `backend/models/connection.py` - 连接模型定义
- `test_db_type_prompt.py` - 测试脚本

## 日期

2026-03-06
