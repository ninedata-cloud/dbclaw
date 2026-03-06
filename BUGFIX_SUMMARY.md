# SmartDBA Bug Fixes Summary - 2026-03-06

本文档总结了今天修复的三个关键bug。

## Bug #1: AI错误选择数据库类型的Skills

### 问题
PostgreSQL和SQL Server数据库在AI诊断时总是先尝试使用MySQL的skills，导致执行失败。

### 根本原因
系统提示词中只告诉AI `connection_id`，但没有告诉AI数据库类型（mysql/postgresql/sqlserver/oracle）。

### 解决方案
修改 `backend/agent/conversation_skills.py`，在系统提示词中添加：
- 数据库类型信息（MYSQL/POSTGRESQL/SQLSERVER/ORACLE）
- Skill前缀映射（postgresql→pg_*, sqlserver→mssql_*）
- 明确指令要求使用对应类型的skills

### 效果
AI现在会收到类似这样的提示：
```
IMPORTANT: This is a POSTGRESQL database. You MUST use pg_* skills
(e.g., pg_get_db_status, pg_get_slow_queries, pg_get_table_stats, etc.).
Do NOT use skills for other database types.
```

### 修改文件
- `backend/agent/conversation_skills.py`

### 详细文档
参见 `BUGFIX_SKILL_SELECTION.md`

---

## Bug #2: SQL Server EXEC语句执行失败

### 问题
在SQL Server中执行 `EXEC sp_configure;` 返回错误：`"error": "name 'any' is not defined"`

### 根本原因
1. **沙箱环境缺少内置函数**：skill执行器的沙箱环境中没有 `any` 和 `all` 函数
2. **不支持EXEC语句**：`execute_diagnostic_query` skill只允许SELECT/SHOW/EXPLAIN，不支持SQL Server的EXEC/EXECUTE

### 解决方案

#### 1. 添加缺失的内置函数
在 `backend/skills/executor.py` 的沙箱环境中添加：
```python
"any": any,
"all": all,
```

#### 2. 扩展支持的SQL语句
修改 `execute_diagnostic_query.yaml`：
- 添加支持：EXEC, EXECUTE, DESCRIBE, DESC
- 更新category: `mysql` → `general`
- 更新描述和标签

### 现在支持的SQL语句
- SELECT: 查询数据（所有数据库）
- SHOW: 显示对象信息（MySQL）
- EXPLAIN: 查询执行计划（所有数据库）
- EXEC/EXECUTE: 执行存储过程（SQL Server, Oracle）
- DESCRIBE/DESC: 描述表结构（MySQL, Oracle）

### 修改文件
- `backend/skills/executor.py`
- `backend/skills/builtin/execute_diagnostic_query.yaml`

### 详细文档
参见 `BUGFIX_EXEC_STATEMENT.md`

---

## Bug #3: SQL Server sql_variant类型不支持

### 问题
查询包含 `sql_variant` 类型的列时返回错误：
```
"error": "('ODBC SQL type -16 is not yet supported.  column-index=1  type=-16', 'HY106')"
```

例如：`SELECT name, value FROM sys.configurations`

### 根本原因
SQL Server的 `sys.configurations` 等系统表使用 `sql_variant` 类型（ODBC类型-16），pyodbc默认不支持这种类型。

### 解决方案

#### 1. 添加sql_variant输出转换器
在 `SQLServerConnector._connect()` 中添加：
```python
def handle_sql_variant(value):
    return str(value) if value is not None else None

conn.add_output_converter(-16, handle_sql_variant)
```

#### 2. 修复连接忙碌问题
在 `execute_query()` 中添加 `cursor.close()` 调用，避免 "Connection is busy" 错误。

### 影响的系统表
- `sys.configurations` - 服务器配置选项
- `sys.extended_properties` - 扩展属性
- 其他使用 `sql_variant` 的系统视图

### 修改文件
- `backend/services/sqlserver_service.py`

### 详细文档
参见 `BUGFIX_SQL_VARIANT.md`

---

## 测试验证

### Bug #1 测试
```bash
python test_db_type_prompt.py
```
验证不同数据库类型的系统提示词生成正确。

### Bug #2 测试
```bash
python test_exec_skill.py
```
验证所有SQL语句类型都能正确通过验证。

### Bug #3 测试
```bash
python test_sql_variant.py
```
验证 sql_variant 类型列可以正常查询。

---

## 影响范围

### Bug #1
- **影响**：所有使用PostgreSQL、SQL Server、Oracle数据库的AI诊断
- **严重性**：高 - 导致诊断失败或延迟
- **修复后**：AI能准确选择正确的数据库特定skills

### Bug #2
- **影响**：SQL Server用户无法执行存储过程进行诊断
- **严重性**：中 - 限制了SQL Server的诊断能力
- **修复后**：支持所有常见的只读诊断SQL语句

### Bug #3
- **影响**：SQL Server用户无法查询系统配置表
- **严重性**：高 - 无法获取关键的配置信息
- **修复后**：可以正常查询所有包含 sql_variant 的系统表

---

## 部署说明

1. 重启后端服务以加载修改后的代码
2. 运行 `python reload_skills.py` 重新加载skills到数据库
3. 测试不同数据库类型的AI诊断功能
4. 特别测试SQL Server的系统表查询

---

## 相关文件

### 修改的代码文件
- `backend/agent/conversation_skills.py`
- `backend/skills/executor.py`
- `backend/skills/builtin/execute_diagnostic_query.yaml`
- `backend/services/sqlserver_service.py`

### 测试文件
- `test_db_type_prompt.py`
- `test_exec_skill.py`
- `test_sql_variant.py`

### 文档文件
- `BUGFIX_SKILL_SELECTION.md`
- `BUGFIX_EXEC_STATEMENT.md`
- `BUGFIX_SQL_VARIANT.md`
- `BUGFIX_SUMMARY.md` (本文件)

---

## 后续建议

1. **监控AI skill选择**：观察AI是否正确选择数据库特定的skills
2. **扩展沙箱函数**：考虑添加更多常用的Python内置函数到沙箱环境
3. **SQL语句白名单**：根据实际使用情况，可能需要添加更多安全的SQL语句类型
4. **单元测试**：为这三个修复添加自动化测试用例
5. **其他ODBC类型**：监控是否有其他不支持的ODBC类型需要添加转换器
6. **性能优化**：考虑为频繁查询的系统表添加缓存

---

修复完成时间：2026-03-06
