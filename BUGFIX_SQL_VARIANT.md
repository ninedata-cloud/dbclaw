# Bug Fix: SQL Server sql_variant类型支持

## 问题描述

在SQL Server中执行包含 `sql_variant` 类型列的查询时返回错误：
```
"error": "('ODBC SQL type -16 is not yet supported.  column-index=1  type=-16', 'HY106')"
```

例如查询：
```sql
SELECT name, value, value_in_use, description FROM sys.configurations ORDER BY name;
```

## 根本原因

SQL Server的 `sys.configurations` 表中的 `value` 和 `value_in_use` 列使用了 `sql_variant` 数据类型。这是一个特殊的类型，可以存储除text、ntext、image、timestamp和sql_variant之外的任何SQL Server数据类型的值。

在ODBC中，`sql_variant` 对应的类型代码是 `-16`，而 **pyodbc 默认不支持这种类型**，导致查询失败。

## 解决方案

在 `backend/services/sqlserver_service.py` 中，为pyodbc连接添加输出转换器（output converter），将 `sql_variant` 类型转换为字符串：

### 修改 `_connect` 方法

```python
def _connect(self):
    import pyodbc
    conn = pyodbc.connect(self._get_conn_string(), autocommit=True)

    # Add output converter for sql_variant type (ODBC type -16)
    # This handles columns like sys.configurations.value
    def handle_sql_variant(value):
        return str(value) if value is not None else None

    conn.add_output_converter(-16, handle_sql_variant)

    return conn
```

### 修改 `execute_query` 方法

同时修复了另一个问题：在查询后需要显式关闭cursor，否则会出现 "Connection is busy with results for another command" 错误。

```python
async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
    import asyncio
    def _exec():
        conn = self._connect()
        try:
            cursor = conn.cursor()
            start = time.time()
            cursor.execute(sql)
            elapsed = round((time.time() - start) * 1000, 2)
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(max_rows)
                result = {
                    "columns": columns,
                    "rows": [list(r) for r in rows],
                    "row_count": len(rows),
                    "execution_time_ms": elapsed,
                    "truncated": len(rows) >= max_rows,
                }
                cursor.close()  # Close cursor to free connection
                return result
            result = {
                "columns": [], "rows": [], "row_count": cursor.rowcount,
                "execution_time_ms": elapsed,
                "message": f"Query OK, {cursor.rowcount} rows affected",
            }
            cursor.close()  # Close cursor to free connection
            return result
        finally:
            conn.close()
    return await asyncio.get_event_loop().run_in_executor(None, _exec)
```

## 技术细节

### pyodbc的add_output_converter

`add_output_converter(sql_type, converter_func)` 方法允许我们为特定的SQL类型注册自定义转换函数：
- `sql_type`: ODBC类型代码（-16 表示 sql_variant）
- `converter_func`: 转换函数，接收原始值，返回Python对象

### sql_variant的值表示

`sql_variant` 在转换为字符串后，会显示为字节序列，例如：
```
b'\\x00\\x00\\x00\\x00'
```

这是因为 `sql_variant` 内部存储了类型信息和实际值。如果需要获取实际的数值，可以在SQL中使用 `CAST` 或 `CONVERT`：
```sql
SELECT name, CAST(value AS VARCHAR(100)) as value_str
FROM sys.configurations
WHERE name = 'max degree of parallelism'
```

## 测试验证

运行测试脚本：
```bash
python test_sql_variant.py
```

测试结果：
```
�� sys.configurations (contains sql_variant columns)
  Columns: ['name', 'value', 'value_in_use', 'description']
  Rows returned: 5
  Execution time: 15.45ms

✓ Simple SELECT
  Columns: ['']
  Rows returned: 1
  Execution time: 11.14ms

✓ Explicit CAST of sql_variant
  Columns: ['name', 'value_str']
  Rows returned: 1
  Execution time: 13.29ms
```

## 影响范围

这个修复影响所有通过 `SQLServerConnector` 执行的查询，包括：
- `execute_diagnostic_query` skill
- 所有SQL Server特定的skills（mssql_*）
- 直接使用 `SQLServerConnector` 的代码

现在可以正常查询包含 `sql_variant` 列的系统表，例如：
- `sys.configurations`
- `sys.sysconfigures`
- 其他使用 `sql_variant` 的系统视图

## 相关SQL Server系统表

常见的包含 `sql_variant` 列的系统表：
- `sys.configurations` - 服务器配置选项
- `sys.extended_properties` - 扩展属性
- `sys.fn_listextendedproperty()` - 扩展属性函数

## 修改文件

- `backend/services/sqlserver_service.py`
  - `_connect()` 方法：添加 sql_variant 输出转换器
  - `execute_query()` 方法：添加 cursor.close() 调用

## 测试文件

- `test_sql_variant.py` - 测试 sql_variant 类型处理

## 参考资料

- [pyodbc add_output_converter](https://github.com/mkleehammer/pyodbc/wiki/Using-an-Output-Converter-function)
- [SQL Server sql_variant](https://learn.microsoft.com/en-us/sql/t-sql/data-types/sql-variant-transact-sql)
- [ODBC SQL Data Types](https://learn.microsoft.com/en-us/sql/odbc/reference/appendixes/sql-data-types)

## 日期

2026-03-06
