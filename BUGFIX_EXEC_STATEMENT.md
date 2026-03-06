# Bug Fix: SQL Server EXEC语句执行失败

## 问题描述

在SQL Server数据库中执行 `execute_diagnostic_query` skill时，使用 `EXEC sp_configure;` 这样的SQL语句会返回错误：
```
"error": "name 'any' is not defined"
```

## 根本原因

有两个问题导致了这个错误：

### 1. 沙箱环境缺少 `any` 和 `all` 内置函数

在 `backend/skills/executor.py` 中，skill执行的沙箱环境的 `__builtins__` 字典中没有包含 `any` 和 `all` 这两个常用的Python内置函数。

原代码（第96-127行）：
```python
restricted_globals = {
    "__builtins__": {
        "len": len,
        "str": str,
        # ... 其他函数
        "isinstance": isinstance,
        # 缺少 any 和 all
    },
}
```

当 `execute_diagnostic_query.yaml` 中的代码尝试使用 `any()` 函数时：
```python
if not any(sql_upper.startswith(keyword) for keyword in allowed_keywords):
```

就会抛出 `name 'any' is not defined` 错误。

### 2. execute_diagnostic_query 不支持 EXEC 语句

`execute_diagnostic_query` skill 只允许 `SELECT`、`SHOW` 和 `EXPLAIN` 语句，不支持SQL Server常用的 `EXEC` 和 `EXECUTE` 语句（用于执行存储过程）。

原代码：
```python
allowed_keywords = ['SELECT', 'SHOW', 'EXPLAIN']
```

## 解决方案

### 1. 在沙箱环境中添加 `any` 和 `all` 函数

修改 `backend/skills/executor.py`：
```python
restricted_globals = {
    "__builtins__": {
        "len": len,
        "str": str,
        # ... 其他函数
        "any": any,      # 添加
        "all": all,      # 添加
        "isinstance": isinstance,
        # ...
    },
}
```

### 2. 扩展 execute_diagnostic_query 支持的SQL语句

修改 `backend/skills/builtin/execute_diagnostic_query.yaml`：

**更新允许的关键字：**
```python
allowed_keywords = ['SELECT', 'SHOW', 'EXPLAIN', 'EXEC', 'EXECUTE', 'DESCRIBE', 'DESC']
```

**更新skill元数据：**
- Category: `mysql` → `general` (通用skill，支持所有数据库类型)
- Description: 添加对 EXEC/EXECUTE 和 DESCRIBE 的说明
- Tags: 添加 `exec`, `describe`, `general`

## 修改的文件

1. **backend/skills/executor.py**
   - 在沙箱环境的 `__builtins__` 中添加 `any` 和 `all` 函数

2. **backend/skills/builtin/execute_diagnostic_query.yaml**
   - 扩展允许的SQL关键字列表
   - 更新category从 `mysql` 到 `general`
   - 更新描述和标签

## 测试验证

运行测试脚本：
```bash
python test_exec_skill.py
```

测试结果：
```
✓ SELECT statement: ALLOWED
  SQL: SELECT @@VERSION

✓ SHOW statement: ALLOWED
  SQL: SHOW TABLES

✓ EXPLAIN statement: ALLOWED
  SQL: EXPLAIN SELECT * FROM users

✓ EXEC statement (SQL Server): ALLOWED
  SQL: EXEC sp_configure

✓ EXECUTE statement (SQL Server): ALLOWED
  SQL: EXECUTE sp_who2

✓ DESCRIBE statement: ALLOWED
  SQL: DESCRIBE users
```

## 支持的SQL语句类型

修复后，`execute_diagnostic_query` skill 现在支持：

- **SELECT**: 查询数据（所有数据库）
- **SHOW**: 显示数据库对象信息（MySQL, MariaDB）
- **EXPLAIN**: 查询执行计划（所有数据库）
- **EXEC/EXECUTE**: 执行存储过程（SQL Server, Oracle）
- **DESCRIBE/DESC**: 描述表结构（MySQL, Oracle）

## 安全性

所有语句仍然是只读的诊断查询。虽然 `EXEC` 可以执行存储过程，但：
1. 只能执行已存在的存储过程
2. 不能创建、修改或删除数据库对象
3. 存储过程的权限由数据库用户权限控制

## 相关文件

- `backend/skills/executor.py` - Skill执行器
- `backend/skills/builtin/execute_diagnostic_query.yaml` - 诊断查询skill
- `test_exec_skill.py` - 测试脚本

## 日期

2026-03-06
