# OceanBase MySQL 内置知识库文档

OCEANBASE_MYSQL_DOCS = [
    {
        "category": "综合诊断",
        "title": "OceanBase MySQL 数据源接入与综合诊断",
        "content": r"""# OceanBase MySQL 数据源接入与综合诊断

## 适用范围

本文适用于 OceanBase MySQL 模式租户的直连监控与诊断。DBClaw 将该类型作为独立数据源展示，但运行时复用 MySQL 协议、MySQL SQL 控制台能力和 `mysql_*` 诊断技能。

## 连接参数

- 数据源类型：OceanBase MySQL
- 默认端口：2883（也可按实际部署填写 2881、3306 或代理端口）
- 数据库名：填写目标业务库；为空时仅做实例级连接测试
- 账号：建议使用只读监控账号，不使用业务写账号

## 基础检查

### 调用 `mysql_get_db_status` skill

```sql
SELECT VERSION();
SHOW GLOBAL STATUS;
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
ORDER BY TIME DESC
LIMIT 20;
```

关注连接数、活跃会话、慢查询计数、网络流量和 InnoDB 相关指标。OceanBase 不同版本对 MySQL 系统表兼容程度不同，若某些指标缺失，应结合 OceanBase 专有视图继续诊断。

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

若该视图不可读，DBClaw 会保留 MySQL 兼容路径结果，并提示补充权限。
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
- `performance_schema.events_statements_summary_by_digest` 不存在或权限不足
- `mysql.slow_log` 不可访问
- `EXPLAIN FORMAT=JSON` 不支持

## 处理策略

DBClaw 首先使用 MySQL 兼容 SQL；失败后尝试 OceanBase 诊断视图；仍失败时返回明确的权限或兼容提示，不应导致数据源基础监控失败。

## 排查顺序

1. 先确认 `SELECT VERSION()` 和 TCP 端口可达。
2. 再确认 `information_schema.PROCESSLIST` 或 `SHOW PROCESSLIST` 可读。
3. TOP SQL 在 OceanBase 场景优先检查 `oceanbase.GV$OB_SQL_AUDIT`（4.x），再检查 `oceanbase.GV$SQL_AUDIT`（3.x）。
4. Explain JSON 不可用时，退回普通 `EXPLAIN` 表格计划。

## 建议

生产环境优先使用 OceanBase 官方代理端口接入，并为 DBClaw 账号授予只读监控权限。若企业安全策略不允许读取 `GV$` 视图，DBClaw 仍可保留连接测试、SQL 控制台和基础 MySQL 兼容指标。
""",
    },
]
