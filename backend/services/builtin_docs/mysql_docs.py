# MySQL 内置知识库文档 - 20篇专业运维诊断文档
# 供 AI 诊断引擎调用，每篇明确标注相关 skill

MYSQL_DOCS = [
    {
        "category": '综合诊断',
        "title": 'MySQL 数据库综合诊断流程',
        "content": r"""# MySQL 数据库综合诊断流程

## 概述

综合诊断是对 MySQL 数据库健康状态进行全面评估的系统化流程，适用于数据库出现未知性能问题、告警触发或周期性巡检场景。从宏观到微观，结合各专项 skill 的调用顺序与判断标准。

## 第一步：快速健康检查

### 调用 `mysql_get_db_status` skill

获取数据库整体运行状态：

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_requests';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_reads';
```

| 指标 | 正常范围 | 告警阈值 | 说明 |
|------|----------|----------|------|
| Threads_running | < CPU核数×2 | > 20 | 活跃线程过多说明并发压力大 |
| Slow_queries 增量 | < 10/分钟 | > 100/分钟 | 慢查询频繁需深入分析 |
| Buffer Pool 命中率 | > 99% | < 95% | 1 - reads/read_requests |
| Aborted_connects 增量 | 接近 0 | > 10/分钟 | 连接失败需检查认证和网络 |

## 第二步：操作系统指标检查

### 调用 `get_os_metrics` skill（需配置 host）

- CPU > 80% 持续 5 分钟 → 进入 CPU 高负载诊断流程
- io_wait > 30% → 进入 IO 性能诊断流程
- 可用内存 < 总内存 10% 且 Swap 在使用 → 内存压力告警

## 第三步：当前会话与锁分析

### 调用 `mysql_get_process_list` skill

```sql
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE COMMAND != 'Sleep'
ORDER BY TIME DESC;
```

重点识别 State = 'Waiting for table metadata lock'（元数据锁）、'Waiting for lock'（行锁）以及大量 Sleep 连接（连接泄漏）。

### 调用 `execute_diagnostic_query` skill 检查 InnoDB 锁等待

```sql
SELECT r.trx_id AS waiting_trx_id, r.trx_mysql_thread_id AS waiting_thread,
  r.trx_query AS waiting_query, b.trx_mysql_thread_id AS blocking_thread,
  b.trx_query AS blocking_query
FROM information_schema.innodb_lock_waits w
INNER JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id
INNER JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id;
```

## 第四步：慢查询分析

### 调用 `mysql_get_slow_queries` skill

获取最近慢查询列表，关注执行时间最长的 SQL、rows_examined 远大于 rows_sent 的全表扫描。

## 第五步：空间使用检查

### 调用 `mysql_get_db_size` skill

```sql
SELECT table_schema,
  ROUND(SUM(data_length + index_length)/1024/1024, 2) AS total_mb,
  ROUND(SUM(data_free)/1024/1024, 2) AS free_mb
FROM information_schema.tables
GROUP BY table_schema ORDER BY total_mb DESC;
```

磁盘使用率 > 80% 立即告警；碎片率 > 30% 建议 OPTIMIZE TABLE。

## 第六步：主从复制检查

### 调用 `mysql_get_replication_status` skill

- Seconds_Behind_Master > 60 → 复制延迟告警
- Slave_IO_Running != Yes 或 Slave_SQL_Running != Yes → 复制中断

## 第七步：关键配置核查

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
```

推荐：innodb_buffer_pool_size 为物理内存的 60~80%，slow_query_log=ON，long_query_time=1。

## 诊断结论模板

1. 健康评分（0-100）
2. 发现的问题（Critical / Warning / Info）
3. 根因分析
4. 优化建议（含具体 SQL 或配置）
5. 跟踪计划"""
    },
    {
        "category": '性能诊断',
        "title": 'MySQL CPU使用高诊断优化流程',
        "content": r"""# MySQL CPU使用高诊断优化流程

## 概述

MySQL CPU 使用率高通常由低效 SQL、不合理并发或配置不当导致。本文档提供系统化的诊断和优化流程。

## 第一步：确认 CPU 高负载

### 调用 `get_os_metrics` skill（需配置 host）

获取操作系统级别 CPU 使用情况，判断 MySQL 进程是否持续 > 80%，是 user 态还是 sys 态，是平稳高负载还是周期性尖刺。

## 第二步：获取当前执行中的 SQL

### 调用 `mysql_get_process_list` skill

```sql
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE COMMAND != 'Sleep' AND TIME > 1
ORDER BY TIME DESC LIMIT 30;
```

高 CPU 典型特征：大量线程处于 executing 或 Sending data，Threads_running 远超 CPU 核心数。

## 第三步：分析慢查询

### 调用 `mysql_get_slow_queries` skill

重点排查全表扫描和排序操作。

### 调用 `mysql_get_db_status` skill 检查临时表开销

```sql
SHOW GLOBAL STATUS LIKE 'Sort_merge_passes';
SHOW GLOBAL STATUS LIKE 'Created_tmp_tables';
SHOW GLOBAL STATUS LIKE 'Created_tmp_disk_tables';
SHOW GLOBAL STATUS LIKE 'Handler_read_rnd_next';
```

- Sort_merge_passes 增量 > 0 → sort_buffer_size 不足
- Created_tmp_disk_tables / Created_tmp_tables > 25% → 临时表溢出磁盘
- Handler_read_rnd_next 极高 → 全表扫描严重

## 第四步：执行计划分析

### 调用 `mysql_explain_query` skill

```sql
EXPLAIN SELECT * FROM orders WHERE customer_id = 12345 AND status = 'pending';
EXPLAIN FORMAT=JSON SELECT ...;
```

| 字段 | 问题标志 | 说明 |
|------|----------|------|
| type | ALL | 全表扫描，严重性能问题 |
| Extra | Using filesort | 文件排序，耗 CPU |
| Extra | Using temporary | 临时表，耗内存和 CPU |
| key | NULL | 未使用索引 |

## 第五步：历史趋势分析

### 调用 `get_metric_history` skill

判断是突发 CPU 飙升（某大 SQL 或批处理任务）还是渐进上升（数据量增长导致 SQL 变慢），以及与业务高峰期的关联。

## 优化方案

### 短期应急

```sql
KILL QUERY <thread_id>;
SET GLOBAL MAX_EXECUTION_TIME = 5000;
```

### 中期优化

```sql
ALTER TABLE orders ADD INDEX idx_customer_status (customer_id, status);
SET GLOBAL sort_buffer_size = 4194304;
SET GLOBAL tmp_table_size = 67108864;
SET GLOBAL max_heap_table_size = 67108864;
```

### 长期优化

1. 启用 Performance Schema 持续监控高耗 CPU 的 SQL
2. 引入读写分离，将分析类查询路由到从库
3. 考虑分区表或归档历史数据减少扫描量
4. 对热点业务引入应用层缓存降低 MySQL 压力"""
    },
    {
        "category": '性能诊断',
        "title": 'MySQL 空间占用高诊断优化流程',
        "content": r"""# MySQL 空间占用高诊断优化流程

## 概述

磁盘空间不足会导致 MySQL 写入失败甚至崩溃，需要及时诊断空间占用高的原因并进行优化。

## 第一步：获取整体空间概览

### 调用 `mysql_get_db_size` skill

```sql
SELECT table_schema AS db_name,
  ROUND(SUM(data_length + index_length)/1024/1024/1024, 3) AS total_gb,
  ROUND(SUM(data_free)/1024/1024/1024, 3) AS fragment_gb
FROM information_schema.tables
GROUP BY table_schema ORDER BY total_gb DESC;

SELECT table_schema, table_name,
  ROUND((data_length + index_length)/1024/1024, 2) AS total_mb,
  ROUND(data_free/(data_length+index_length+1)*100, 1) AS fragment_pct
FROM information_schema.tables
ORDER BY total_mb DESC LIMIT 20;
```

## 第二步：检查操作系统磁盘使用

### 调用 `get_os_metrics` skill（需配置 host）

重点检查 MySQL 数据目录磁盘使用率、binlog 占用、undo log 占用、tmpdir 使用情况。

## 第三步：检查 binlog 空间占用

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'expire_logs_days';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

expire_logs_days=0 且 binlog_expire_logs_seconds=0 → binlog 永不自动清理，危险。

```sql
PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY);
```

## 第四步：检查 InnoDB 表碎片

### 调用 `mysql_get_table_stats` skill

碎片率（fragment_pct）> 30% 的表建议重建：

```sql
OPTIMIZE TABLE large_table;  -- 会锁表，建议低峰期
ALTER TABLE large_table ENGINE=InnoDB;  -- 等效，支持在线 DDL
```

## 第五步：检查大事务和 undo log

### 调用 `execute_diagnostic_query` skill

```sql
SELECT trx_id, trx_started, trx_rows_modified,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS running_sec
FROM information_schema.innodb_trx
ORDER BY running_sec DESC;

SHOW GLOBAL STATUS LIKE 'Innodb_history_list_length';
```

Innodb_history_list_length > 10000 → 有长事务未提交，undo log 无法清理，会持续占用空间。

## 第六步：检查临时表和错误日志

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'innodb_temp_data_file_path';
SHOW VARIABLES LIKE 'general_log';
SHOW VARIABLES LIKE 'general_log_file';
```

general_log=ON 会产生大量日志，生产环境应关闭。

## 优化建议

1. 设置合理的 binlog 保留策略（7天以内）
2. 定期对高碎片表执行 OPTIMIZE TABLE
3. 及时终止长事务，避免 undo log 膨胀
4. 关闭 general_log，定期轮转 slow_log
5. 使用分区表对历史数据按时间分区，便于按分区删除
6. 考虑数据归档：将超过 6 个月的历史数据迁移到归档表或对象存储"""
    },
    {
        "category": '性能诊断',
        "title": 'MySQL 网络流量高诊断优化流程',
        "content": r"""# MySQL 网络流量高诊断优化流程

## 概述

MySQL 网络流量高会导致网卡带宽饱和，影响响应时间和吞吐量。常见原因包括大结果集查询、频繁的小查询、binlog 同步流量等。

## 第一步：确认网络流量高

### 调用 `get_os_metrics` skill（需配置 host）

获取网卡 RX/TX 流量，判断是入流量高（写入为主）还是出流量高（查询结果集为主）。

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Bytes_sent';
SHOW GLOBAL STATUS LIKE 'Bytes_received';
SHOW GLOBAL STATUS LIKE 'Questions';
```

计算：
- 平均每次查询发送字节数 = Bytes_sent / Questions
- 若 > 100KB/次 → 存在大结果集查询

## 第二步：定位大结果集查询

### 调用 `mysql_get_process_list` skill

```sql
SELECT ID, USER, DB, TIME, STATE, LENGTH(INFO) AS sql_len, INFO
FROM information_schema.PROCESSLIST
WHERE COMMAND = 'Query' AND STATE = 'Sending data'
ORDER BY TIME DESC;
```

处于 Sending data 状态的长时间会话，往往是大结果集的来源。

### 调用 `mysql_get_slow_queries` skill

关注 rows_sent 极大的慢查询，这类 SQL 会产生大量网络流量。

## 第三步：检查连接数和查询频率

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Com_select';
SHOW GLOBAL STATUS LIKE 'Com_insert';
SHOW GLOBAL STATUS LIKE 'Connections';
```

若 Com_select 极高但单次 Bytes_sent 不大 → 是查询频率过高导致的流量，考虑缓存层。

## 第四步：检查主从复制流量

### 调用 `mysql_get_replication_status` skill

```sql
SHOW SLAVE STATUS\G
SHOW MASTER STATUS;
SHOW BINARY LOGS;
```

主从复制 binlog 同步也会消耗网络带宽，尤其是大事务或批量写入时。

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'slave_compressed_protocol';
```

slave_compressed_protocol=OFF → 开启压缩可减少复制流量约 30~50%。

## 第五步：历史趋势分析

### 调用 `get_metric_history` skill

对比网络流量与查询量、连接数的历史趋势，判断流量增长与业务增长的关联。

## 优化方案

### 减少大结果集

```sql
-- 强制分页，避免 SELECT *
SELECT id, name, status FROM orders
WHERE created_at > '2024-01-01'
LIMIT 1000 OFFSET 0;

-- 只查询需要的列
SELECT id, total_amount FROM orders WHERE user_id = 123;
```

### 开启压缩

```sql
-- 开启主从复制压缩
SET GLOBAL slave_compressed_protocol = ON;

-- 应用层使用压缩协议连接（连接串添加 compress=true）
```

### 引入缓存层

对高频但结果变化不大的查询，在应用层引入缓存层，减少直接访问 MySQL 的次数。

### 数据库连接优化

合并小查询、使用 batch insert、减少不必要的 SELECT COUNT(*) 轮询。"""
    },
    {
        "category": '性能诊断',
        "title": 'MySQL SQL诊断优化流程',
        "content": r"""# MySQL SQL诊断优化流程

## 概述

SQL 性能问题是 MySQL 最常见的故障根因。本文档提供从识别问题 SQL 到执行计划分析、索引优化的完整流程。

## 第一步：识别问题 SQL

### 调用 `mysql_get_slow_queries` skill

慢查询日志是发现问题 SQL 的首要工具：

```sql
-- 查看慢查询配置
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'slow_query_log_file';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'log_queries_not_using_indexes';
```

如果未开启，立即开启：
```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;
SET GLOBAL log_queries_not_using_indexes = ON;
```

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Slow_queries';
SHOW GLOBAL STATUS LIKE 'Select_full_join';
SHOW GLOBAL STATUS LIKE 'Select_scan';
```

- Select_full_join > 0 → 存在无索引 JOIN，极危险
- Select_scan 增量大 → 全表扫描频繁

## 第二步：执行计划分析

### 调用 `mysql_explain_query` skill

```sql
EXPLAIN SELECT o.id, o.total, c.name
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.status = 'pending'
  AND o.created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY o.created_at DESC
LIMIT 100;
```

EXPLAIN 输出关键字段解读：

| 字段 | 优 | 差 |
|------|----|----- |
| type | const/ref/range | ALL/index |
| key | 有值 | NULL |
| rows | 小 | 极大 |
| Extra | Using index | Using filesort / Using temporary |

```sql
-- 获取更详细的执行计划
EXPLAIN FORMAT=JSON SELECT ...;

-- MySQL 8.0 可用 EXPLAIN ANALYZE 获取实际执行统计
EXPLAIN ANALYZE SELECT ...;
```

## 第三步：索引分析

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看表索引
SHOW INDEX FROM orders;

-- 查看索引使用情况（需要 Performance Schema）
SELECT object_schema, object_name, index_name,
  count_star, count_read, count_write
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE object_schema = 'mydb'
  AND index_name IS NOT NULL
ORDER BY count_star ASC;
```

count_star 为 0 的索引是从未使用过的冗余索引，可以考虑删除。

## 第四步：SQL 改写优化

常见优化模式：

### 避免在索引列上使用函数

```sql
-- 差：函数导致索引失效
SELECT * FROM orders WHERE DATE(created_at) = '2024-01-01';

-- 优：范围查询利用索引
SELECT * FROM orders
WHERE created_at >= '2024-01-01'
  AND created_at < '2024-01-02';
```

### 避免隐式类型转换

```sql
-- 差：字符串与数字比较，索引失效
SELECT * FROM user WHERE phone = 13800138000;

-- 优：类型一致
SELECT * FROM user WHERE phone = '13800138000';
```

### 优化分页查询

```sql
-- 差：OFFSET 大时性能差
SELECT * FROM orders ORDER BY id LIMIT 100000, 20;

-- 优：游标分页
SELECT * FROM orders WHERE id > 100000 ORDER BY id LIMIT 20;
```

## 第五步：添加索引

```sql
-- 复合索引（最左前缀原则）
ALTER TABLE orders ADD INDEX idx_status_created (status, created_at);

-- 覆盖索引（避免回表）
ALTER TABLE orders ADD INDEX idx_covering (customer_id, status, total_amount);

-- 在线 DDL（MySQL 5.6+）
ALTER TABLE orders ADD INDEX idx_new (col1, col2), ALGORITHM=INPLACE, LOCK=NONE;
```"""
    },
    {
        "category": '性能诊断',
        "title": 'MySQL 写入慢诊断优化流程',
        "content": r"""# MySQL 写入慢诊断优化流程

## 概述

MySQL 写入性能问题（INSERT/UPDATE/DELETE 慢）会直接影响业务可用性。常见原因包括锁竞争、索引过多、刷盘策略、事务太大等。

## 第一步：确认写入慢的现象

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_waits';
SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_time_avg';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_wait_free';
SHOW GLOBAL STATUS LIKE 'Innodb_log_waits';
SHOW GLOBAL STATUS LIKE 'Com_insert';
SHOW GLOBAL STATUS LIKE 'Com_update';
SHOW GLOBAL STATUS LIKE 'Com_delete';
```

- Innodb_row_lock_waits 增量大 → 行锁竞争严重
- Innodb_log_waits > 0 → redo log 写入等待，I/O 瓶颈
- Innodb_buffer_pool_wait_free > 0 → buffer pool 页面不够用

## 第二步：查看当前阻塞

### 调用 `mysql_get_process_list` skill

```sql
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE STATE IN (
  'Waiting for lock',
  'Waiting for table lock',
  'Waiting for table metadata lock',
  'update'
)
ORDER BY TIME DESC;
```

### 调用 `execute_diagnostic_query` skill 查看事务状态

```sql
SELECT trx_id, trx_state, trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS running_sec,
  trx_rows_locked, trx_rows_modified, trx_query
FROM information_schema.innodb_trx
ORDER BY running_sec DESC;
```

## 第三步：检查 IO 性能

### 调用 `get_os_metrics` skill（需配置 host）

检查磁盘 I/O 使用率，io_wait > 30% 说明写入受 IO 限制。

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'sync_binlog';
SHOW VARIABLES LIKE 'innodb_io_capacity';
SHOW VARIABLES LIKE 'innodb_flush_method';
```

| 参数 | 安全值 | 高性能值 | 说明 |
|------|--------|----------|------|
| innodb_flush_log_at_trx_commit | 1 | 2 | 2 表示每秒刷盘，可能丢失 1 秒数据 |
| sync_binlog | 1 | 0 | 0 表示 OS 控制刷盘 |

## 第四步：检查索引数量

### 调用 `execute_diagnostic_query` skill

```sql
SELECT table_schema, table_name, COUNT(*) AS index_count
FROM information_schema.statistics
WHERE table_schema NOT IN ('information_schema','mysql','performance_schema')
GROUP BY table_schema, table_name
HAVING index_count > 6
ORDER BY index_count DESC;
```

索引过多会拖慢写入，每次写入都需要维护所有索引。

## 第五步：检查慢写入 SQL

### 调用 `mysql_get_slow_queries` skill

慢查询日志记录 DML 操作，重点关注 UPDATE/DELETE 影响行数大的操作。

## 优化方案

### 减少锁竞争

```sql
-- 批量写入改为小批次
INSERT INTO orders (...) VALUES (...),(...),...;  -- 每批 500~1000 行

-- 避免长事务，及时 COMMIT
START TRANSACTION;
-- 操作
COMMIT;  -- 不要拖延提交
```

### 优化刷盘策略（非严格一致性场景）

```sql
SET GLOBAL innodb_flush_log_at_trx_commit = 2;
SET GLOBAL sync_binlog = 100;
```

### 删除冗余索引

```sql
ALTER TABLE orders DROP INDEX idx_unused;
```"""
    },
    {
        "category": '性能诊断',
        "title": 'MySQL 索引优化诊断流程',
        "content": r"""# MySQL 索引优化诊断流程

## 概述

索引是 MySQL 性能优化的核心手段。合理的索引可以将查询从全表扫描优化为精确查找，但过多或不合理的索引也会拖慢写入。本文档提供索引诊断和优化的完整流程。

## 第一步：发现缺失索引

### 调用 `mysql_get_slow_queries` skill

慢查询日志中的 SQL 往往是缺失索引的直接线索。结合 rows_examined 与 rows_sent 的比值判断是否全表扫描。

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Handler_read_rnd_next';
SHOW GLOBAL STATUS LIKE 'Handler_read_rnd';
SHOW GLOBAL STATUS LIKE 'Select_scan';
SHOW GLOBAL STATUS LIKE 'Select_full_join';
```

- Handler_read_rnd_next 增量大 → 大量全表扫描
- Select_full_join > 0 → JOIN 无索引，危险

## 第二步：分析执行计划

### 调用 `mysql_explain_query` skill

```sql
EXPLAIN SELECT * FROM orders o
JOIN user u ON o.user_id = u.id
WHERE o.status = 'pending' AND o.created_at > '2024-01-01';
```

type 列判断标准（从好到差）：
- system/const → 最优，单行查询
- eq_ref → 联表唯一索引
- ref → 非唯一索引
- range → 索引范围扫描
- index → 全索引扫描（次优）
- ALL → 全表扫描（最差）

## 第三步：检查冗余索引

### 调用 `execute_diagnostic_query` skill

```sql
-- 查找重复索引（前缀相同）
SELECT
  s1.table_schema, s1.table_name,
  s1.index_name AS index1,
  s2.index_name AS index2,
  s1.column_name
FROM information_schema.statistics s1
JOIN information_schema.statistics s2
  ON s1.table_schema = s2.table_schema
  AND s1.table_name = s2.table_name
  AND s1.column_name = s2.column_name
  AND s1.seq_in_index = s2.seq_in_index
  AND s1.index_name != s2.index_name
WHERE s1.table_schema NOT IN ('information_schema','mysql','performance_schema')
ORDER BY s1.table_schema, s1.table_name;

-- 查找从未使用的索引（需 Performance Schema）
SELECT object_schema, object_name, index_name
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE index_name IS NOT NULL
  AND count_star = 0
  AND object_schema NOT IN ('mysql','performance_schema')
ORDER BY object_schema, object_name;
```

## 第四步：索引设计原则

### 复合索引最左前缀原则

```sql
-- 索引 (a, b, c) 可用于：
-- WHERE a = ?
-- WHERE a = ? AND b = ?
-- WHERE a = ? AND b = ? AND c = ?
-- 但不能用于：
-- WHERE b = ?  （跳过最左列）
-- WHERE a = ? AND c = ?  （跳过中间列）

ALTER TABLE orders ADD INDEX idx_user_status_date (user_id, status, created_at);
```

### 覆盖索引

```sql
-- 查询只涉及索引列，无需回表
SELECT user_id, status, total_amount
FROM orders
WHERE user_id = 123
  AND status = 'paid';

-- 为此查询创建覆盖索引
ALTER TABLE orders ADD INDEX idx_covering (user_id, status, total_amount);
```

### 前缀索引（长字符串列）

```sql
-- 对长文本列使用前缀索引
ALTER TABLE user ADD INDEX idx_email_prefix (email(20));

-- 计算合适的前缀长度
SELECT COUNT(DISTINCT LEFT(email, 10)) / COUNT(*) AS selectivity FROM user;
```

## 第五步：在线添加/删除索引

```sql
-- MySQL 5.6+ 在线 DDL
ALTER TABLE orders
  ADD INDEX idx_status_date (status, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;

-- 删除冗余索引
ALTER TABLE orders DROP INDEX idx_redundant;

-- pt-online-schema-change（大表推荐）
-- pt-osc --alter "ADD INDEX idx_new (col1, col2)" D=mydb,t=orders
```"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL 死锁诊断优化流程',
        "content": r"""# MySQL 死锁诊断优化流程

## 概述

死锁是两个或多个事务互相持有对方需要的锁，导致永久等待。MySQL InnoDB 会自动检测死锁并回滚代价较小的事务，但频繁死锁会严重影响业务可用性。

## 第一步：确认死锁发生

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_deadlocks';
```

Innodb_deadlocks 增量 > 0 说明存在死锁。

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看最近一次死锁详情
SHOW ENGINE INNODB STATUS\G
```

重点关注 LATEST DETECTED DEADLOCK 部分，包含：
- 死锁涉及的事务
- 各事务持有的锁和等待的锁
- 被回滚的事务

## 第二步：分析死锁日志

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'innodb_print_all_deadlocks';
SHOW VARIABLES LIKE 'log_error';
```

开启死锁日志记录到错误日志：
```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

## 第三步：查看当前锁状态

### 调用 `execute_diagnostic_query` skill

```sql
-- 当前等待的锁
SELECT
  r.trx_id AS waiting_trx,
  r.trx_mysql_thread_id AS waiting_thread,
  r.trx_query AS waiting_query,
  b.trx_id AS blocking_trx,
  b.trx_mysql_thread_id AS blocking_thread,
  b.trx_query AS blocking_query,
  TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) AS wait_sec
FROM information_schema.innodb_lock_waits w
JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id
JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id
ORDER BY wait_sec DESC;

-- MySQL 8.0 使用 performance_schema
SELECT * FROM performance_schema.data_lock_waits\G
```

## 第四步：分析死锁根因

常见死锁模式：

### 1. 事务操作顺序相反

```
事务A: UPDATE orders WHERE id=1 → UPDATE orders WHERE id=2
事务B: UPDATE orders WHERE id=2 → UPDATE orders WHERE id=1
```

解决：统一所有事务对同一组资源的操作顺序。

### 2. 间隙锁（Gap Lock）冲突

```sql
-- RR 隔离级别下，范围查询持有间隙锁
SELECT * FROM orders WHERE id BETWEEN 10 AND 20 FOR UPDATE;
```

解决：降低隔离级别为 READ COMMITTED，或缩小查询范围。

### 3. 批量操作顺序不一致

```sql
-- 批量 UPDATE 应按主键顺序操作
UPDATE orders SET status='done' WHERE id IN (3,1,2);  -- 危险：顺序随机
UPDATE orders SET status='done' WHERE id IN (1,2,3);  -- 安全：按 id 顺序
```

## 第五步：预防措施

```sql
-- 1. 合理设置锁等待超时
SET GLOBAL innodb_lock_wait_timeout = 10;

-- 2. 降低隔离级别（可接受幻读时）
SET GLOBAL transaction_isolation = 'READ-COMMITTED';

-- 3. 减小事务粒度，及时提交
-- 4. 批量操作按主键排序
-- 5. 使用 SELECT ... FOR UPDATE 时注意加锁顺序
```"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL 连接失败诊断流程',
        "content": r"""# MySQL 连接失败诊断流程

## 概述

连接失败是 MySQL 最紧急的故障之一，直接导致业务不可用。原因可能包括连接数耗尽、认证失败、网络问题、MySQL 服务异常等。

## 第一步：快速判断故障类型

连接失败的常见错误码：

| 错误码 | 错误信息 | 根因 |
|--------|----------|------|
| 1040 | Too many connections | 连接数耗尽 |
| 1045 | Access denied | 用户名/密码/IP 错误 |
| 2003 | Can't connect to MySQL server | MySQL 未启动或网络不通 |
| 2013 | Lost connection | 连接超时或网络中断 |
| 1129 | Host is blocked | 连接失败次数过多被封锁 |

## 第二步：检查连接数状态

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Connection_errors_max_connections';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Aborted_clients';
```

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'wait_timeout';
SHOW VARIABLES LIKE 'interactive_timeout';
```

若 Threads_connected 接近 max_connections → 立即处理：

```sql
-- 临时增加连接数上限
SET GLOBAL max_connections = 1000;

-- 清理 Sleep 连接
SELECT CONCAT('KILL ', id, ';')
FROM information_schema.PROCESSLIST
WHERE COMMAND = 'Sleep' AND TIME > 300;
```

## 第三步：查看当前连接分布

### 调用 `mysql_get_process_list` skill

```sql
SELECT USER, HOST, DB, COMMAND,
  COUNT(*) AS cnt,
  MAX(TIME) AS max_time
FROM information_schema.PROCESSLIST
GROUP BY USER, HOST, DB, COMMAND
ORDER BY cnt DESC;
```

识别哪个用户/IP/数据库占用连接最多。

## 第四步：检查认证问题

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看用户权限
SELECT user, host, plugin, account_locked, password_expired
FROM mysql.user
WHERE user NOT IN ('mysql.sys','mysql.session','mysql.infoschema');

-- 检查被封锁的 host
SELECT * FROM performance_schema.host_cache
WHERE sum_connect_errors > 0
ORDER BY sum_connect_errors DESC;

-- 解封被封锁的 host
FLUSH HOSTS;
```

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'max_connect_errors';
```

若某个 host 连续失败次数 > max_connect_errors，该 host 会被封锁。设置更大的值或使用 FLUSH HOSTS 解封。

## 第五步：检查网络和服务状态

### 调用 `get_os_metrics` skill（需配置 host）

```bash
netstat -an | grep 3306
ss -tlnp | grep mysqld
tcpdump -i eth0 port 3306 -c 100
```

检查 MySQL 是否监听在预期端口，是否有防火墙拦截。

## 第六步：历史趋势分析

### 调用 `get_metric_history` skill

查看连接数历史趋势，判断是突发增长还是长期趋势，以便评估是否需要扩容或优化连接池配置。

## 优化建议

1. 应用层使用连接池（HikariCP、Druid），避免频繁建立新连接
2. 设置合理的 wait_timeout（建议 60~300 秒）
3. max_connections 不宜过大，每个连接消耗约 1MB 内存
4. 部署 ProxySQL 或 MyCAT 作为连接代理，多路复用连接"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL SQL执行失败诊断流程',
        "content": r"""# MySQL SQL执行失败诊断流程

## 概述

SQL 执行失败会直接导致业务异常。本文档覆盖常见 SQL 错误的诊断和解决方法，包括语法错误、权限错误、约束违反、资源不足等场景。

## 常见 SQL 错误分类

| 错误码 | 说明 | 处理方向 |
|--------|------|----------|
| 1064 | SQL 语法错误 | 检查 SQL 语法 |
| 1146 | 表不存在 | 检查表名和数据库 |
| 1054 | 列不存在 | 检查字段名 |
| 1062 | 主键/唯一键冲突 | 检查数据重复 |
| 1452 | 外键约束失败 | 检查父表数据 |
| 1205 | 锁等待超时 | 检查锁竞争 |
| 1213 | 死锁 | 重试或优化事务 |
| 1366 | 数据类型不匹配 | 检查字段类型 |
| 1406 | 数据太长 | 检查字段长度 |
| 1292 | 日期值不正确 | 检查日期格式 |

## 第一步：收集错误信息

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Com_rollback';
SHOW GLOBAL STATUS LIKE 'Handler_rollback';
SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_waits';
```

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看最近的错误
SHOW WARNINGS;
SHOW ERRORS;

-- 查看 MySQL 错误日志路径
SHOW VARIABLES LIKE 'log_error';
```

## 第二步：锁相关错误诊断（错误码 1205/1213）

### 调用 `mysql_get_process_list` skill

查找持有锁的会话：

```sql
SELECT * FROM information_schema.PROCESSLIST
WHERE State LIKE '%lock%'
ORDER BY TIME DESC;
```

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看 InnoDB 锁等待
SELECT
  r.trx_mysql_thread_id AS waiting_thread,
  r.trx_query AS waiting_sql,
  b.trx_mysql_thread_id AS blocking_thread,
  b.trx_query AS blocking_sql,
  TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) AS wait_sec
FROM information_schema.innodb_lock_waits w
JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id
JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id;
```

解决：KILL 阻塞会话，或设置更大的 innodb_lock_wait_timeout。

## 第三步：约束错误诊断（错误码 1062/1452）

### 调用 `execute_diagnostic_query` skill

```sql
-- 查询重复数据
SELECT email, COUNT(*) AS cnt
FROM user GROUP BY email HAVING cnt > 1;

-- 查看表约束
SHOW CREATE TABLE orders\G

-- 查看外键约束
SELECT
  TABLE_NAME, CONSTRAINT_NAME,
  REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'mydb'
  AND REFERENCED_TABLE_NAME IS NOT NULL;
```

## 第四步：权限错误诊断（错误码 1142/1044）

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看用户权限
SHOW GRANTS FOR 'appuser'@'%';

-- 授予权限
GRANT SELECT, INSERT, UPDATE, DELETE ON mydb.* TO 'appuser'@'%';
FLUSH PRIVILEGES;
```

## 第五步：资源不足错误

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'max_allowed_packet';
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW VARIABLES LIKE 'net_read_timeout';
SHOW VARIABLES LIKE 'net_write_timeout';
```

```sql
-- 调整 max_allowed_packet（大 BLOB 写入失败时）
SET GLOBAL max_allowed_packet = 67108864;  -- 64MB
```"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL 主备延时诊断流程',
        "content": r"""# MySQL 主备延时诊断流程

## 概述

主备延时（Replication Lag）是指从库应用 binlog 的进度落后于主库的时间差。延时过大会导致读写分离场景下从库数据不一致，影响业务正确性。

## 第一步：确认延时状态

### 调用 `mysql_get_replication_status` skill

```sql
SHOW SLAVE STATUS\G
```

关键字段解读：

| 字段 | 说明 | 判断标准 |
|------|------|----------|
| Slave_IO_Running | IO 线程状态 | 必须为 Yes |
| Slave_SQL_Running | SQL 线程状态 | 必须为 Yes |
| Seconds_Behind_Master | 复制延时（秒） | > 60 需关注，> 300 告警 |
| Master_Log_File | 正在读取的主库 binlog | 与主库对比 |
| Read_Master_Log_Pos | 已读取的位置 | 与主库对比 |
| Exec_Master_Log_Pos | 已执行的位置 | 落后越多延时越大 |
| Last_SQL_Error | SQL 线程最近错误 | 非空则需立即处理 |

## 第二步：判断延时原因

### 场景一：主库写入压力大（binlog 产生速度 > 从库应用速度）

### 调用 `mysql_get_db_status` skill（在主库执行）

```sql
SHOW MASTER STATUS;
SHOW GLOBAL STATUS LIKE 'Binlog_cache_use';
SHOW GLOBAL STATUS LIKE 'Com_insert';
SHOW GLOBAL STATUS LIKE 'Com_update';
SHOW GLOBAL STATUS LIKE 'Com_delete';
```

主库写入 QPS 极高时，从库单线程应用 binlog 可能跟不上。

### 场景二：从库执行慢查询

### 调用 `mysql_get_slow_queries` skill（在从库执行）

从库执行某些复杂 SQL 耗时远超主库（因为主库有索引缓存热数据，从库可能没有）。

### 场景三：大事务

### 调用 `execute_diagnostic_query` skill

```sql
-- 查找大事务（在主库）
SELECT trx_id, trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS running_sec,
  trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY running_sec DESC LIMIT 10;
```

大事务（如批量 UPDATE 百万行）在主库可能很快，但从库需要串行应用整个事务。

## 第三步：检查从库资源

### 调用 `get_os_metrics` skill（在从库执行，需配置 host）

检查从库 CPU、IO 是否成为瓶颈。从库 io_wait 高说明磁盘性能不足以支撑 binlog 应用速度。

## 第四步：检查并行复制配置

### 调用 `mysql_get_db_variables` skill（在从库执行）

```sql
SHOW VARIABLES LIKE 'slave_parallel_workers';
SHOW VARIABLES LIKE 'slave_parallel_type';
SHOW VARIABLES LIKE 'binlog_transaction_dependency_tracking';
```

**开启多线程并行复制（MySQL 5.7+）：**

```sql
STOP SLAVE SQL_THREAD;
SET GLOBAL slave_parallel_type = 'LOGICAL_CLOCK';
SET GLOBAL slave_parallel_workers = 8;
SET GLOBAL binlog_transaction_dependency_tracking = 'WRITESET';
START SLAVE SQL_THREAD;
```

## 第五步：历史趋势分析

### 调用 `get_metric_history` skill

查看延时历史曲线，判断是持续延时还是周期性尖刺（与主库批处理任务吻合）。

## 应急处理

```sql
-- 临时跳过错误（谨慎使用）
STOP SLAVE;
SET GLOBAL SQL_SLAVE_SKIP_COUNTER = 1;
START SLAVE;

-- 查看延时减少趋势
WATCH -n 1 'mysql -e "SHOW SLAVE STATUS\G" | grep Seconds_Behind_Master'
```"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL 主备数据不一致诊断流程',
        "content": r"""# MySQL 主备数据不一致诊断流程

## 概述

主备数据不一致是 MySQL 高可用场景中的严重问题，可能导致主从切换后数据丢失或业务错误。本文档提供检测和修复主备不一致的完整流程。

## 第一步：确认复制状态

### 调用 `mysql_get_replication_status` skill

```sql
SHOW SLAVE STATUS\G
```

重点检查：
- Slave_IO_Running 和 Slave_SQL_Running 是否均为 Yes
- Last_SQL_Error 是否有错误（如 1062 主键冲突、1032 找不到记录）
- Seconds_Behind_Master 是否合理

常见导致不一致的错误：
- Error 1062：从库已存在该记录（可能有人直接写了从库）
- Error 1032：从库找不到主库要更新/删除的记录

## 第二步：检查 binlog 格式

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'enforce_gtid_consistency';
```

- binlog_format = STATEMENT → 存在不一致风险（UUID()、NOW() 等函数在主从执行结果不同）
- 推荐使用 ROW 格式，确保主从操作完全一致

## 第三步：使用工具检测不一致

### 调用 `get_os_metrics` skill（需配置 host）

使用 pt-table-checksum 检测主备数据一致性：

```bash
# 在主库执行
pt-table-checksum \
  --host=master_ip \
  --user=checker \
  --password=xxx \
  --databases=mydb \
  --tables=orders,user \
  --replicate=mydb.checksums

# 查看不一致的表
pt-table-checksum --replicate-check-only
```

## 第四步：修复数据不一致

### 调用 `execute_diagnostic_query` skill

**方法一：跳过错误（小范围不一致）**

```sql
-- 跳过当前错误事务
STOP SLAVE;
SET GLOBAL SQL_SLAVE_SKIP_COUNTER = 1;
START SLAVE;
```

**方法二：pt-table-sync 修复（推荐）**

```bash
# 将主库数据同步到从库
pt-table-sync \
  --execute \
  --sync-to-master \
  h=slave_ip,D=mydb,t=orders
```

**方法三：重建从库（严重不一致）**

```bash
# 1. 在主库做全量备份
mysqldump --master-data=2 --single-transaction \
  -u root -p mydb > backup.sql

# 2. 在从库恢复
mysql -u root -p mydb < backup.sql

# 3. 根据 backup.sql 中的 CHANGE MASTER TO 重新配置复制
```

## 第五步：预防措施

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'read_only';
SHOW VARIABLES LIKE 'super_read_only';
```

从库应设置 read_only=ON 和 super_read_only=ON，防止误写从库导致数据不一致。

```sql
SET GLOBAL read_only = ON;
SET GLOBAL super_read_only = ON;
```

其他预防措施：
1. 使用 GTID 复制模式，便于精确追踪复制位点
2. 使用 ROW 格式 binlog
3. 定期运行 pt-table-checksum 巡检
4. 禁止直接操作从库数据"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL 启动失败诊断流程',
        "content": r"""# MySQL 启动失败诊断流程

## 概述

MySQL 启动失败是严重的运维事故，需要快速定位原因并恢复服务。常见原因包括配置错误、数据文件损坏、端口冲突、权限问题等。

## 第一步：查看错误日志

### 调用 `get_os_metrics` skill（需配置 host）

错误日志是诊断启动失败的首要依据：

```bash
# 查看 MySQL 错误日志
tail -100 /var/log/mysql/error.log
tail -100 /var/log/mysqld.log

# 查看 systemd 日志
journalctl -u mysqld -n 100 --no-pager
systemctl status mysqld
```

常见错误信息及含义：

| 错误信息 | 原因 | 解决方向 |
|----------|------|----------|
| Can't start server: Bind on TCP/IP port | 端口被占用 | 检查 3306 端口 |
| InnoDB: Tablespace id in file doesn't match | 数据文件不匹配 | 检查 innodb_data_file_path |
| Fatal error: Can't open and lock privilege tables | mysql 系统表损坏 | 运行 mysql_upgrade |
| [ERROR] InnoDB: Unable to lock ./ibdata1 | 锁文件存在（上次未正常关闭） | 删除 .pid 文件 |
| Table './mysql/user' is marked as crashed | 系统表损坏 | 修复系统表 |

## 第二步：检查端口冲突

```bash
netstat -tlnp | grep 3306
ss -tlnp | grep 3306
lsof -i :3306

# 如果端口被占用，找出占用进程
fuser 3306/tcp
```

## 第三步：检查文件权限和磁盘空间

```bash
# 检查数据目录权限
ls -la /var/lib/mysql/
stat /var/lib/mysql/

# 应为 mysql:mysql 所有
chown -R mysql:mysql /var/lib/mysql/

# 检查磁盘空间
df -h

# 检查 inode
df -i
```

磁盘空间满或 inode 耗尽都会导致 MySQL 无法启动。

## 第四步：检查配置文件

```bash
# 验证配置文件语法
mysqld --verbose --help 2>&1 | head -50

# 查看当前使用的配置文件
mysqld --print-defaults

# 检查关键配置
grep -E 'innodb_buffer_pool_size|max_connections|datadir|socket' /etc/mysql/my.cnf
```

常见配置错误：
- innodb_buffer_pool_size 超过物理内存 → OOM 导致启动失败
- datadir 路径不存在或无权限
- socket 文件路径无写权限

## 第五步：InnoDB 恢复模式

如果是 InnoDB 数据文件损坏，可尝试强制恢复：

```ini
# 在 my.cnf 中添加（逐步从 1 增加到 6）
[mysqld]
innodb_force_recovery = 1
```

恢复级别说明：
- 1：忽略损坏的页
- 2：阻止主线程运行
- 3：不回滚事务
- 4：不执行 insert buffer merge
- 5：不前滚已提交事务
- 6：不回滚未提交事务

**注意：** 设置 innodb_force_recovery > 0 后，立即备份数据，不要执行写操作。

```bash
# 启动后立即导出数据
mysqldump --all-databases > emergency_backup.sql
```

## 第六步：系统表修复

```bash
# 修复系统表
mysql_upgrade -u root -p

# 或者重新初始化数据目录（会丢失数据，谨慎操作）
mysqld --initialize --user=mysql
```"""
    },
    {
        "category": '故障排查',
        "title": 'MySQL 数据丢失恢复方案',
        "content": r"""# MySQL 数据丢失恢复方案

## 概述

数据丢失是最严重的数据库事故。本文档提供从 binlog、备份文件恢复数据的完整方案，以及预防数据丢失的最佳实践。

## 数据丢失的常见原因

1. 误执行 DELETE/UPDATE 无 WHERE 条件
2. 误删表（DROP TABLE）
3. 误删数据库（DROP DATABASE）
4. 硬件故障导致数据文件损坏
5. MySQL 异常崩溃且 innodb_flush_log_at_trx_commit != 1

## 第一步：立即止损

### 调用 `mysql_get_process_list` skill

立即查看是否有正在进行的危险操作，并 KILL 掉：

```sql
SELECT ID, USER, HOST, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE INFO LIKE '%DROP%'
   OR INFO LIKE '%DELETE%'
   OR INFO LIKE '%TRUNCATE%'
ORDER BY TIME DESC;

KILL QUERY <thread_id>;
```

如果是生产数据库，考虑立即将数据库设置为只读，防止进一步数据写入覆盖：

```sql
SET GLOBAL read_only = ON;
```

## 第二步：确认 binlog 状态

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'datadir';
SHOW BINARY LOGS;
SHOW MASTER STATUS;
```

## 第三步：从 binlog 恢复

### 调用 `get_os_metrics` skill（需配置 host）

```bash
# 查找误操作时间点附近的 binlog
mysqlbinlog --start-datetime='2024-01-15 14:00:00' \
            --stop-datetime='2024-01-15 14:30:00' \
            /var/lib/mysql/binlog.000123 | head -200

# 找到误操作的 position（如 DROP TABLE 在 pos 12345）
mysqlbinlog --start-position=1 --stop-position=12344 \
            /var/lib/mysql/binlog.000123 > recovery.sql

# 应用恢复 SQL
mysql -u root -p mydb < recovery.sql
```

**GTID 模式下的恢复：**

```bash
mysqlbinlog --include-gtids='xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:1-1000' \
            --exclude-gtids='xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:999' \
            binlog.000123 > recovery.sql
```

## 第四步：从备份恢复

**mysqldump 备份恢复：**

```bash
# 恢复整库
mysql -u root -p < full_backup.sql

# 恢复单表
mysql -u root -p mydb < orders_backup.sql

# 提取单表（从全库备份中）
sed -n '/CREATE TABLE `orders`/,/CREATE TABLE/p' full_backup.sql > orders_only.sql
```

**xtrabackup 备份恢复：**

```bash
# 准备备份
xtrabackup --prepare --target-dir=/backup/full/

# 恢复
xtrabackup --copy-back --target-dir=/backup/full/
chown -R mysql:mysql /var/lib/mysql/
```

## 第五步：结合备份和 binlog 的时间点恢复（PITR）

```bash
# 1. 恢复最近一次全量备份（假设备份时间为昨天凌晨2点）
mysql -u root -p < /backup/full_20240114_0200.sql

# 2. 应用备份后到误操作前的 binlog
mysqlbinlog \
  --start-datetime='2024-01-14 02:00:00' \
  --stop-datetime='2024-01-15 14:05:00' \
  /var/lib/mysql/binlog.* | mysql -u root -p

# 3. 恢复完成，验证数据
SELECT COUNT(*) FROM mydb.orders;
```

## 预防措施

1. 开启 binlog 并设置合理保留期（至少 7 天）
2. 定期全量备份（mysqldump 或 xtrabackup）
3. 备份验证：定期演练恢复流程
4. 生产环境 SQL 审核：禁止无 WHERE 条件的 DELETE/UPDATE
5. 使用 SQL 审计工具拦截高风险操作
6. 从库设置 read_only，防止误操作"""
    },
    {
        "category": '配置与会话',
        "title": 'MySQL 系统参数配置诊断优化流程',
        "content": r"""# MySQL 系统参数配置诊断优化流程

## 概述

MySQL 有数百个系统参数，合理的参数配置是数据库稳定高性能运行的基础。本文档提供关键参数的诊断和优化建议。

## 第一步：获取当前配置

### 调用 `mysql_get_db_variables` skill

```sql
-- 内存相关
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW VARIABLES LIKE 'key_buffer_size';
SHOW VARIABLES LIKE 'query_cache_size';
SHOW VARIABLES LIKE 'sort_buffer_size';
SHOW VARIABLES LIKE 'join_buffer_size';
SHOW VARIABLES LIKE 'read_buffer_size';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';

-- 连接相关
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'wait_timeout';
SHOW VARIABLES LIKE 'interactive_timeout';
SHOW VARIABLES LIKE 'max_connect_errors';

-- InnoDB 相关
SHOW VARIABLES LIKE 'innodb_log_file_size';
SHOW VARIABLES LIKE 'innodb_log_buffer_size';
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'innodb_flush_method';
SHOW VARIABLES LIKE 'innodb_io_capacity';
SHOW VARIABLES LIKE 'innodb_read_io_threads';
SHOW VARIABLES LIKE 'innodb_write_io_threads';

-- 日志相关
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'expire_logs_days';
```

## 第二步：评估 Buffer Pool 命中率

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_requests';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_reads';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_total';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_free';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_dirty';
```

计算命中率：
```
命中率 = 1 - (Innodb_buffer_pool_reads / Innodb_buffer_pool_read_requests)
```

命中率 < 99% → 需要增大 innodb_buffer_pool_size。

## 第三步：关键参数优化建议

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| innodb_buffer_pool_size | 物理内存 × 70% | 最重要的参数，越大越好 |
| innodb_buffer_pool_instances | 8~16 | 减少 buffer pool 锁竞争 |
| innodb_log_file_size | 1~4GB | 太小导致频繁刷盘 |
| innodb_flush_log_at_trx_commit | 1（安全）/ 2（性能） | 1 最安全，2 性能更好 |
| innodb_flush_method | O_DIRECT | 避免双重缓存 |
| innodb_io_capacity | SSD: 2000~10000 | 根据磁盘 IOPS 设置 |
| max_connections | 500~2000 | 太大消耗内存 |
| wait_timeout | 60~300 | 避免连接泄漏 |
| slow_query_log | ON | 生产必须开启 |
| long_query_time | 1 | 记录超过 1 秒的查询 |

## 第四步：应用配置修改

```sql
-- 在线修改（重启后失效，需写入 my.cnf）
SET GLOBAL innodb_buffer_pool_size = 8589934592;  -- 8GB
SET GLOBAL max_connections = 1000;
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;
SET GLOBAL wait_timeout = 300;
```

修改 my.cnf（持久化）：

```ini
[mysqld]
innodb_buffer_pool_size = 8G
innodb_buffer_pool_instances = 8
innodb_log_file_size = 2G
innodb_flush_log_at_trx_commit = 1
innodb_flush_method = O_DIRECT
max_connections = 1000
wait_timeout = 300
slow_query_log = ON
long_query_time = 1
```

## 第五步：验证配置效果

### 调用 `get_metric_history` skill

修改配置后，通过历史指标对比修改前后的性能变化（Buffer Pool 命中率、QPS、响应时间）。"""
    },
    {
        "category": '配置与会话',
        "title": 'MySQL 会话连接诊断优化流程',
        "content": r"""# MySQL 会话连接诊断优化流程

## 概述

会话连接管理是 MySQL 稳定性的重要保障。连接泄漏、连接数耗尽、长时间空闲连接都会导致资源浪费和服务不可用。

## 第一步：查看当前连接概况

### 调用 `mysql_get_process_list` skill

```sql
-- 连接总览
SELECT
  COMMAND,
  COUNT(*) AS cnt,
  AVG(TIME) AS avg_time,
  MAX(TIME) AS max_time
FROM information_schema.PROCESSLIST
GROUP BY COMMAND
ORDER BY cnt DESC;

-- 按用户和来源分组
SELECT
  USER, SUBSTRING_INDEX(HOST, ':', 1) AS client_ip,
  COUNT(*) AS connections,
  SUM(CASE WHEN COMMAND='Sleep' THEN 1 ELSE 0 END) AS sleep_cnt
FROM information_schema.PROCESSLIST
GROUP BY USER, client_ip
ORDER BY connections DESC;
```

## 第二步：检查连接数配置

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Threads_cached';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Aborted_clients';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
```

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'thread_cache_size';
SHOW VARIABLES LIKE 'wait_timeout';
SHOW VARIABLES LIKE 'interactive_timeout';
SHOW VARIABLES LIKE 'net_read_timeout';
SHOW VARIABLES LIKE 'net_write_timeout';
```

**判断标准：**
- Threads_connected / max_connections > 80% → 连接数告警
- Aborted_clients 持续增长 → 应用层连接池配置问题
- 大量 Sleep 连接且 TIME 极大 → wait_timeout 设置过大，连接泄漏

## 第三步：识别问题连接

### 调用 `execute_diagnostic_query` skill

```sql
-- 空闲超过 10 分钟的连接
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE
FROM information_schema.PROCESSLIST
WHERE COMMAND = 'Sleep' AND TIME > 600
ORDER BY TIME DESC;

-- 长时间运行的查询
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE COMMAND != 'Sleep' AND TIME > 30
ORDER BY TIME DESC;

-- 生成 KILL 语句
SELECT CONCAT('KILL ', ID, ';') AS kill_cmd
FROM information_schema.PROCESSLIST
WHERE COMMAND = 'Sleep' AND TIME > 1800;
```

## 第四步：分析长时间运行的事务

### 调用 `execute_diagnostic_query` skill

```sql
SELECT
  p.ID AS thread_id,
  p.USER, p.HOST, p.DB,
  t.trx_id,
  t.trx_state,
  TIMESTAMPDIFF(SECOND, t.trx_started, NOW()) AS trx_duration_sec,
  t.trx_rows_locked,
  t.trx_rows_modified,
  p.INFO AS current_sql
FROM information_schema.innodb_trx t
JOIN information_schema.PROCESSLIST p ON t.trx_mysql_thread_id = p.ID
ORDER BY trx_duration_sec DESC;
```

## 第五步：优化连接管理

### 调整超时参数

```sql
-- 缩短空闲连接超时
SET GLOBAL wait_timeout = 300;      -- 非交互连接 5 分钟
SET GLOBAL interactive_timeout = 300; -- 交互连接 5 分钟

-- 增大线程缓存减少连接建立开销
SET GLOBAL thread_cache_size = 100;
```

### 应用层连接池优化建议

| 参数 | 推荐设置 | 说明 |
|------|----------|------|
| 最小连接数 | 10~20 | 预热连接，避免冷启动 |
| 最大连接数 | 50~200 | 根据业务并发量设置 |
| 连接有效性检测 | 开启 | 防止使用失效连接 |
| 空闲超时 | 180s | 小于 MySQL wait_timeout |
| 最大等待时间 | 3000ms | 超时快速失败，避免请求堆积 |

### 使用 ProxySQL 连接代理

对于连接数极大的场景（> 1000 并发），建议引入 ProxySQL 实现连接多路复用，将后端 MySQL 的实际连接数控制在合理范围内。"""
    },
    {
        "category": '安全与权限',
        "title": 'MySQL 安全诊断方案',
        "content": r"""# MySQL 安全诊断方案

## 概述

MySQL 安全诊断涵盖用户权限、网络访问、数据加密、审计日志等多个维度。定期进行安全诊断是防范数据泄露和入侵的重要措施。

## 第一步：检查用户账号安全

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看所有用户账号
SELECT
  User, Host, plugin,
  account_locked,
  password_expired,
  password_last_changed,
  IF(authentication_string='', 'NO_PASSWORD', 'HAS_PASSWORD') AS has_pwd
FROM mysql.user
ORDER BY User;

-- 检查空密码账号
SELECT User, Host FROM mysql.user
WHERE authentication_string = '' OR authentication_string IS NULL;

-- 检查 root 账号是否允许远程访问
SELECT User, Host FROM mysql.user
WHERE User = 'root' AND Host != 'localhost';

-- 检查匿名账号
SELECT User, Host FROM mysql.user WHERE User = '';
```

**高风险发现：**
- 存在空密码账号 → 立即设置密码或删除
- root 允许 % 远程访问 → 限制为 localhost 或特定 IP
- 存在匿名账号 → 立即删除

## 第二步：检查权限最小化原则

### 调用 `execute_diagnostic_query` skill

```sql
-- 拥有 SUPER 权限的用户
SELECT User, Host FROM mysql.user
WHERE Super_priv = 'Y' AND User NOT IN ('root');

-- 拥有 GRANT OPTION 的用户
SELECT User, Host, Grant_priv FROM mysql.user WHERE Grant_priv = 'Y';

-- 全局 ALL 权限的用户
SELECT User, Host FROM mysql.user
WHERE Select_priv='Y' AND Insert_priv='Y' AND Update_priv='Y'
  AND Delete_priv='Y' AND Create_priv='Y' AND Drop_priv='Y'
  AND User NOT IN ('root');

-- 查看具体用户权限
SHOW GRANTS FOR 'appuser'@'%';
```

## 第三步：检查网络访问配置

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'bind_address';
SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'local_infile';
SHOW VARIABLES LIKE 'secure_file_priv';
SHOW VARIABLES LIKE 'skip_networking';
```

**安全配置要求：**
- bind_address 不应为 0.0.0.0（除非有防火墙保护）
- local_infile = OFF（防止 LOAD DATA LOCAL INFILE 攻击）
- secure_file_priv 应设置为特定目录

## 第四步：检查 SSL/TLS 配置

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'have_ssl';
SHOW VARIABLES LIKE 'ssl_ca';
SHOW VARIABLES LIKE 'ssl_cert';
SHOW VARIABLES LIKE 'ssl_key';
SHOW VARIABLES LIKE 'require_secure_transport';
```

```sql
-- 查看使用非 SSL 连接的用户
SELECT User, Host, ssl_type FROM mysql.user WHERE ssl_type = '';

-- 要求用户必须使用 SSL
ALTER USER 'appuser'@'%' REQUIRE SSL;
```

## 第五步：检查审计日志

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'general_log';
SHOW VARIABLES LIKE 'general_log_file';
SHOW VARIABLES LIKE 'audit_log_file';
```

## 安全加固清单

```sql
-- 1. 删除匿名账号
DELETE FROM mysql.user WHERE User = '';

-- 2. 删除 test 数据库
DROP DATABASE IF EXISTS test;
DELETE FROM mysql.db WHERE Db='test' OR Db='test\_%';

-- 3. 修改默认端口（my.cnf）
-- port = 33306

-- 4. 关闭 local_infile
SET GLOBAL local_infile = OFF;

-- 5. 应用权限
FLUSH PRIVILEGES;
```"""
    },
    {
        "category": '安全与权限',
        "title": 'MySQL 用户权限诊断方案',
        "content": r"""# MySQL 用户权限诊断方案

## 概述

合理的用户权限管理是 MySQL 安全的核心。本文档提供用户权限的诊断、审计和优化方案，遵循最小权限原则。

## 第一步：梳理现有用户

### 调用 `execute_diagnostic_query` skill

```sql
-- 完整用户列表
SELECT
  User, Host,
  plugin AS auth_plugin,
  account_locked,
  password_expired,
  Create_priv, Drop_priv, Grant_priv,
  Super_priv, Repl_slave_priv
FROM mysql.user
ORDER BY User, Host;

-- 数据库级别权限
SELECT User, Host, Db,
  Select_priv, Insert_priv, Update_priv,
  Delete_priv, Create_priv, Drop_priv, Index_priv, Alter_priv
FROM mysql.db
ORDER BY User, Db;

-- 表级别权限
SELECT User, Host, Db, Table_name,
  Table_priv, Column_priv
FROM mysql.tables_priv
ORDER BY User, Db, Table_name;
```

## 第二步：识别高风险权限

### 调用 `execute_diagnostic_query` skill

```sql
-- SUPER 权限用户
SELECT User, Host FROM mysql.user WHERE Super_priv = 'Y';

-- FILE 权限用户（可读写服务器文件）
SELECT User, Host FROM mysql.user WHERE File_priv = 'Y';

-- PROCESS 权限用户（可查看所有连接和 SQL）
SELECT User, Host FROM mysql.user WHERE Process_priv = 'Y';

-- REPLICATION SLAVE 权限
SELECT User, Host FROM mysql.user WHERE Repl_slave_priv = 'Y';

-- 拥有 SHUTDOWN 权限
SELECT User, Host FROM mysql.user WHERE Shutdown_priv = 'Y';
```

**高风险权限说明：**

| 权限 | 风险 | 建议 |
|------|------|------|
| SUPER | 绕过大多数限制 | 仅 DBA 账号拥有 |
| FILE | 读写服务器文件 | 应用账号不应拥有 |
| GRANT OPTION | 可授权给他人 | 严格控制 |
| REPLICATION SLAVE | 复制权限 | 仅从库账号拥有 |

## 第三步：权限最小化改造

### 调用 `execute_diagnostic_query` skill

```sql
-- 创建应用只读账号
CREATE USER 'app_readonly'@'192.168.1.%'
  IDENTIFIED BY 'StrongPassword123!';
GRANT SELECT ON mydb.* TO 'app_readonly'@'192.168.1.%';

-- 创建应用读写账号（无建表删表权限）
CREATE USER 'app_rw'@'192.168.1.%'
  IDENTIFIED BY 'StrongPassword456!';
GRANT SELECT, INSERT, UPDATE, DELETE ON mydb.* TO 'app_rw'@'192.168.1.%';

-- 创建 DBA 账号（完整权限，仅限内网）
CREATE USER 'dba'@'10.0.0.%'
  IDENTIFIED BY 'DBAPassword789!';
GRANT ALL PRIVILEGES ON *.* TO 'dba'@'10.0.0.%' WITH GRANT OPTION;

-- 创建只读复制账号
CREATE USER 'replicator'@'10.0.0.%'
  IDENTIFIED BY 'ReplPassword!';
GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'10.0.0.%';

FLUSH PRIVILEGES;
```

## 第四步：撤销多余权限

```sql
-- 撤销 FILE 权限
REVOKE FILE ON *.* FROM 'appuser'@'%';

-- 撤销 SUPER 权限
REVOKE SUPER ON *.* FROM 'appuser'@'%';

-- 将全局权限降为库级权限
REVOKE ALL PRIVILEGES ON *.* FROM 'appuser'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON mydb.* TO 'appuser'@'%';

FLUSH PRIVILEGES;
```

## 第五步：密码策略管理

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'validate_password%';
SHOW VARIABLES LIKE 'default_password_lifetime';
```

```sql
-- 开启密码强度验证
INSTALL PLUGIN validate_password SONAME 'validate_password.so';
SET GLOBAL validate_password_policy = 'MEDIUM';
SET GLOBAL validate_password_length = 10;

-- 设置密码过期策略（90天）
ALTER USER 'appuser'@'%' PASSWORD EXPIRE INTERVAL 90 DAY;

-- 修改用户密码
ALTER USER 'appuser'@'%' IDENTIFIED BY 'NewStrongPassword!';
FLUSH PRIVILEGES;
```

## 权限诊断结论

完成诊断后输出：
1. 高风险账号清单（空密码、ROOT远程访问、过多权限）
2. 建议撤销的权限列表
3. 建议创建的专用账号方案
4. 密码策略加固建议"""
    },
    {
        "category": '技术参考',
        "title": 'MySQL binlog技术细节',
        "content": r"""# MySQL binlog技术细节

## 概述

binlog（Binary Log）是 MySQL 的核心日志，用于主从复制、数据恢复和审计。理解 binlog 的技术细节对于 DBA 进行故障排查和性能优化至关重要。

## binlog 的三种格式

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_value_options';
```

| 格式 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| STATEMENT | 记录原始 SQL | 日志量小 | 不确定性函数可能导致主从不一致 |
| ROW | 记录行变更前后的数据 | 精确，无不一致风险 | 日志量大（批量操作） |
| MIXED | 自动选择 STATEMENT 或 ROW | 兼顾大小和一致性 | 复杂，调试难度高 |

推荐生产环境使用 ROW 格式，配合 binlog_row_image=MINIMAL 减少日志量。

## binlog 关键配置参数

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW VARIABLES LIKE 'binlog_cache_size';
SHOW VARIABLES LIKE 'max_binlog_size';
SHOW VARIABLES LIKE 'expire_logs_days';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'sync_binlog';
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'enforce_gtid_consistency';
```

关键参数说明：
- sync_binlog=1：每次事务提交都将 binlog 刷盘，最安全但性能略低
- max_binlog_size：单个 binlog 文件最大大小（默认 1GB）
- expire_logs_days：binlog 自动清理天数（建议 7 天）

## 查看 binlog 内容

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看 binlog 文件列表
SHOW BINARY LOGS;

-- 查看主库当前 binlog 位置
SHOW MASTER STATUS;

-- 查看 binlog 事件
SHOW BINLOG EVENTS IN 'binlog.000123' FROM 100 LIMIT 50;
```

### 调用 `get_os_metrics` skill（需配置 host）

```bash
# 解析 binlog 文件内容
mysqlbinlog /var/lib/mysql/binlog.000123 | head -200

# 按时间范围解析
mysqlbinlog --start-datetime='2024-01-15 14:00:00'             --stop-datetime='2024-01-15 15:00:00'             /var/lib/mysql/binlog.000123

# 以 ROW 格式可读方式输出
mysqlbinlog -v --base64-output=DECODE-ROWS binlog.000123
```

## GTID 模式

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'gtid_executed';
SHOW VARIABLES LIKE 'gtid_purged';
```

GTID（Global Transaction Identifier）格式：`server_uuid:transaction_id`

GTID 优势：
1. 主从切换时无需手动计算 binlog 位点
2. 可以精确识别已执行的事务，避免重复执行
3. 简化主从搭建流程

```sql
-- 启用 GTID（需在 my.cnf 中配置）
-- gtid_mode = ON
-- enforce_gtid_consistency = ON
-- log_slave_updates = ON
```

## binlog 监控

### 调用 `mysql_get_db_status` skill

```sql
SHOW GLOBAL STATUS LIKE 'Binlog_cache_use';
SHOW GLOBAL STATUS LIKE 'Binlog_cache_disk_use';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache_use';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache_disk_use';
```

Binlog_cache_disk_use > 0 说明 binlog_cache_size 不足，事务 binlog 溢出到磁盘，应增大 binlog_cache_size。

## 清理 binlog

```sql
-- 手动清理指定日期前的 binlog
PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY);

-- 清理到指定文件前
PURGE BINARY LOGS TO 'binlog.000100';

-- 设置自动清理
SET GLOBAL expire_logs_days = 7;
```

注意：清理前确认所有从库已应用这些 binlog（通过 SHOW SLAVE STATUS 确认 Master_Log_File）。"""
    },
    {
        "category": '技术参考',
        "title": 'MySQL 错误码查询',
        "content": r"""# MySQL 错误码查询

## 概述

MySQL 错误码是快速定位问题的重要线索。本文档整理了最常见的 MySQL 错误码、含义、诊断方向和解决方案，并说明如何通过 skill 辅助诊断。

## 连接类错误

| 错误码 | 错误名称 | 含义 | 解决方案 |
|--------|----------|------|----------|
| 1040 | ER_CON_COUNT_ERROR | 连接数超限 | 增大 max_connections 或优化连接池 |
| 1045 | ER_ACCESS_DENIED_ERROR | 认证失败 | 检查用户名、密码、HOST 权限 |
| 1129 | ER_HOST_IS_BLOCKED | HOST 被封锁 | 执行 FLUSH HOSTS |
| 2003 | CR_CONN_HOST_ERROR | 无法连接到服务器 | 检查 MySQL 是否运行、防火墙设置 |
| 2013 | CR_SERVER_LOST | 连接在查询中丢失 | 检查 net_read_timeout、net_write_timeout |
| 2006 | CR_SERVER_GONE_ERROR | MySQL 服务器已关闭 | 检查 wait_timeout，应用需重连 |

### 调用 `mysql_get_db_status` skill 诊断连接问题

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Connection_errors_max_connections';
```

## 权限类错误

| 错误码 | 错误名称 | 含义 | 解决方案 |
|--------|----------|------|----------|
| 1142 | ER_TABLEACCESS_DENIED_ERROR | 表权限不足 | GRANT 相应权限 |
| 1044 | ER_DBACCESS_DENIED_ERROR | 数据库权限不足 | GRANT 数据库权限 |
| 1227 | ER_SPECIFIC_ACCESS_DENIED_ERROR | 需要特定权限（如 SUPER） | 授予或使用有权限账号 |

### 调用 `execute_diagnostic_query` skill 诊断权限问题

```sql
SHOW GRANTS FOR CURRENT_USER();
SHOW GRANTS FOR 'appuser'@'%';
```

## 数据约束类错误

| 错误码 | 错误名称 | 含义 | 解决方案 |
|--------|----------|------|----------|
| 1062 | ER_DUP_ENTRY | 唯一键冲突 | 检查重复数据，使用 INSERT IGNORE 或 ON DUPLICATE KEY |
| 1452 | ER_NO_REFERENCED_ROW_2 | 外键约束失败（父表无记录） | 先插入父表数据 |
| 1451 | ER_ROW_IS_REFERENCED_2 | 外键约束失败（子表有引用） | 先删除子表数据 |
| 1406 | ER_DATA_TOO_LONG | 数据超过列长度 | 检查字段定义或截断数据 |
| 1366 | ER_TRUNCATED_WRONG_VALUE | 数据类型不匹配 | 检查插入数据类型 |
| 1292 | ER_TRUNCATED_WRONG_VALUE_FOR_FIELD | 日期/时间值不正确 | 检查日期格式（YYYY-MM-DD） |

## 锁与事务类错误

| 错误码 | 错误名称 | 含义 | 解决方案 |
|--------|----------|------|----------|
| 1205 | ER_LOCK_WAIT_TIMEOUT | 锁等待超时 | 检查锁竞争，KILL 阻塞会话 |
| 1213 | ER_LOCK_DEADLOCK | 死锁 | 应用层重试，优化事务顺序 |
| 1614 | ER_GTID_UNSAFE_STATEMENT | GTID 不安全语句 | 修改 SQL 或调整 enforce_gtid_consistency |

### 调用 `mysql_get_process_list` skill 诊断锁问题

```sql
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE STATE LIKE '%lock%' OR STATE LIKE '%wait%'
ORDER BY TIME DESC;
```

### 调用 `execute_diagnostic_query` skill

```sql
SHOW ENGINE INNODB STATUS\G
```

## 资源类错误

| 错误码 | 错误名称 | 含义 | 解决方案 |
|--------|----------|------|----------|
| 1114 | ER_RECORD_FILE_FULL | 表空间已满 | 清理数据或扩展磁盘 |
| 1021 | ER_DISK_FULL | 磁盘空间不足 | 立即清理磁盘空间 |
| 1038 | ER_OUT_OF_SORTMEMORY | 排序内存不足 | 增大 sort_buffer_size |
| 1104 | ER_TOO_BIG_SELECT | 查询结果集超限 | 添加 LIMIT 或优化查询 |

### 调用 `mysql_get_db_variables` skill

```sql
SHOW VARIABLES LIKE 'max_allowed_packet';
SHOW VARIABLES LIKE 'sort_buffer_size';
SHOW VARIABLES LIKE 'innodb_data_file_path';
```

## 复制类错误

| 错误码 | 错误名称 | 含义 | 解决方案 |
|--------|----------|------|----------|
| 1032 | ER_KEY_NOT_FOUND | 从库找不到要更新的行 | 跳过错误或重建从库 |
| 1062 | ER_DUP_ENTRY | 从库主键冲突 | 跳过错误或重建从库 |
| 1236 | ER_MASTER_FATAL_ERROR | 读取 binlog 错误 | 检查主库 binlog 完整性 |

### 调用 `mysql_get_replication_status` skill

```sql
SHOW SLAVE STATUS\G
-- 关注 Last_SQL_Error 和 Last_IO_Error 字段
```

## 错误码查询命令

```bash
# 命令行查询错误码含义
perror 1205
mysqld --verbose --help 2>&1 | grep -A2 "1205"

# MySQL 8.0 错误参考
mysql -e "SELECT * FROM mysql.global_variables WHERE VARIABLE_NAME='error_count';"
```"""
    }
]
