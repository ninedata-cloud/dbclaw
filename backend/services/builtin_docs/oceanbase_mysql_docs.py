# OceanBase MySQL 内置知识库文档

OCEANBASE_MYSQL_DOCS = [
    {
        "category": "综合诊断",
        "title": "OceanBase MySQL 数据源接入与综合诊断",
        "content": r"""# OceanBase MySQL 数据源接入与综合诊断

## 适用范围

本文适用于 OceanBase MySQL 模式租户的直连监控与诊断。DBClaw 将该类型作为独立数据源处理，使用 `oceanbase_mysql_*` 诊断技能，并将 OceanBase 专有诊断 SQL 与 MySQL 诊断能力隔离。

## 连接参数

- 数据源类型：OceanBase MySQL
- 默认端口：2883（也可按实际部署填写 2881、3306 或代理端口）
- 数据库名：填写目标业务库；为空时仅做实例级连接测试
- 账号：建议使用只读监控账号，不使用业务写账号

## 基础检查

### 调用 `oceanbase_mysql_get_db_status` skill

```sql
SELECT VERSION();
SHOW GLOBAL STATUS;
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
ORDER BY TIME DESC
LIMIT 20;
```

关注连接数、活跃会话、慢查询计数、网络流量和缓存命中率等指标。OceanBase 不同版本对部分基础状态变量支持程度不同，若某些指标缺失，应结合 OceanBase 专有视图继续诊断。

## OceanBase 增强诊断

当账号具备权限时，可读取 OceanBase 诊断视图：

```sql
-- OceanBase 4.x
SELECT query_sql, sql_id, elapsed_time, request_time
FROM oceanbase.GV$OB_SQL_AUDIT
WHERE query_sql IS NOT NULL
ORDER BY request_time DESC
LIMIT 20;

-- OceanBase 3.x
SELECT query_sql, sql_id, elapsed_time, request_time
FROM oceanbase.GV$SQL_AUDIT
WHERE query_sql IS NOT NULL
ORDER BY request_time DESC
LIMIT 20;
```

若该视图不可读，`oceanbase_mysql_get_top_sql` 与 `oceanbase_mysql_get_slow_queries` 会返回明确权限提示；基础连接测试、SQL 控制台和基础状态采集仍可继续使用。
""",
    },
    {
        "category": "安全与权限",
        "title": "OceanBase MySQL 监控账号权限建议",
        "content": r"""# OceanBase MySQL 监控账号权限建议

## 最小权限目标

监控账号应满足连接测试、只读 SQL 控制台、基础指标采集和慢 SQL/TOP SQL 诊断，避免授予写权限或高危管理权限。

## 推荐权限

```sql
CREATE USER dbclaw_mon IDENTIFIED BY 'strong_password';
GRANT SELECT ON *.* TO dbclaw_mon;
```

如需读取 OceanBase 诊断视图，请按企业权限规范补充对 `oceanbase` 系统库或相关 `GV$` 视图的只读权限。

## 验证 SQL

```sql
SELECT VERSION();
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SELECT COUNT(*) FROM information_schema.PROCESSLIST;
SELECT query_sql FROM oceanbase.GV$OB_SQL_AUDIT LIMIT 1; -- OceanBase 4.x
SELECT query_sql FROM oceanbase.GV$SQL_AUDIT LIMIT 1;    -- OceanBase 3.x
```

最后两条根据实例版本选择验证即可；若对应版本视图不可读，不影响基础直连能力，但 TOP SQL/慢 SQL 的 OceanBase 增强信息会受限。
""",
    },
    {
        "category": "故障排查",
        "title": "OceanBase MySQL 兼容性与降级处理",
        "content": r"""# OceanBase MySQL 兼容性与降级处理

## 常见现象

- `SHOW GLOBAL STATUS` 部分变量缺失
- `oceanbase.GV$OB_SQL_AUDIT` 不存在或权限不足
- `oceanbase.GV$SQL_AUDIT` 不存在或权限不足
- `EXPLAIN FORMAT=JSON` 不支持

## 处理策略

DBClaw 使用独立的 OceanBase MySQL connector 和 `oceanbase_mysql_*` 技能。基础状态、会话和对象元数据通过 MySQL 模式可读的系统表采集；慢 SQL/TOP SQL 等增强诊断通过 OceanBase `GV$` 视图采集。

## 排查顺序

1. 先确认 `SELECT VERSION()` 和 TCP 端口可达。
2. 再确认 `information_schema.PROCESSLIST` 或 `SHOW PROCESSLIST` 可读。
3. TOP SQL 在 OceanBase 场景优先检查 `oceanbase.GV$OB_SQL_AUDIT`（4.x），再检查 `oceanbase.GV$SQL_AUDIT`（3.x）。
4. Explain JSON 不可用时，退回普通 `EXPLAIN` 表格计划。

## 建议

生产环境优先使用 OceanBase 官方代理端口接入，并为 DBClaw 账号授予只读监控权限。若企业安全策略不允许读取 `GV$` 视图，DBClaw 仍可保留连接测试、SQL 控制台和基础状态指标。
""",
    },
]
