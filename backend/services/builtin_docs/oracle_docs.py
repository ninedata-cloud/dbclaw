# Oracle 内置知识库文档 - 20篇专业运维诊断文档
# 供 AI 诊断引擎调用，每篇明确标注相关 skill

ORACLE_DOCS = [
    {
        "category": "综合诊断",
        "title": "Oracle 数据库综合诊断流程",
        "content": r"""# Oracle 数据库综合诊断流程

## 概述

Oracle 数据库综合诊断是对数据库运行状态的全面评估，涵盖实例状态、性能瓶颈、等待事件、空间使用、会话连接、归档日志、Data Guard 复制以及告警日志等多个维度。本文档提供系统化的诊断流程，帮助 DBA 快速定位并解决问题。

## 诊断技能调用顺序

1. `get_db_status` — 获取实例基本状态
2. `get_process_list` — 查看当前会话与等待事件
3. `get_slow_queries` — 识别高资源消耗 SQL
4. `get_db_size` — 检查表空间与数据文件使用情况
5. `get_os_metrics` — 获取主机 CPU / 内存 / IO 资源（需配置 host）
6. `get_replication_status` — 检查 Data Guard 同步状态
7. `execute_diagnostic_query` — 执行自定义诊断 SQL

## 第一步：实例状态检查

### 调用 `get_db_status` skill

```sql
-- 实例基本信息
SELECT instance_name, status, database_status, archiver,
       version, startup_time
FROM v$instance;

-- 数据库基本信息
SELECT name, db_unique_name, log_mode, open_mode,
       protection_mode, database_role
FROM v$database;
```

**判断标准**：

| 指标 | 正常值 | 异常处理 |
|---|---|---|
| STATUS | OPEN | MOUNTED/NOMOUNT 需查实例启动日志 |
| DATABASE_STATUS | ACTIVE | SUSPENDED 需检查 I/O 挂起 |
| ARCHIVER | STARTED | STOPPED 需立即处理归档空间 |
| LOG_MODE | ARCHIVELOG | 生产环境必须开归档 |
| OPEN_MODE | READ WRITE | READ ONLY 为备库或恢复模式 |

## 第二步：等待事件与会话分析

### 调用 `get_process_list` skill

```sql
-- 当前活跃会话及等待事件
SELECT s.sid, s.serial#, s.username, s.status,
       s.wait_class, s.event, s.seconds_in_wait,
       s.sql_id, s.machine, s.program
FROM v$session s
WHERE s.status = 'ACTIVE'
  AND s.username IS NOT NULL
ORDER BY s.seconds_in_wait DESC;

-- 系统级等待事件汇总（排除空闲等待）
SELECT wait_class, event, total_waits, time_waited,
       ROUND(time_waited/GREATEST(total_waits,1), 2) avg_wait_ms
FROM v$system_event
WHERE wait_class != 'Idle'
ORDER BY time_waited DESC
FETCH FIRST 20 ROWS ONLY;
```

**常见高危等待事件**：

| 等待事件 | 含义 | 处理方向 |
|---|---|---|
| db file sequential read | 单块随机读（索引扫描） | 检查索引有效性 |
| log file sync | LGWR 写日志等待 | 优化 Redo 配置 |
| enq: TX - row lock contention | 行锁争用 | 排查长事务 |
| library cache lock | 共享池解析锁 | 检查 SQL 硬解析 |
| buffer busy waits | 缓冲区忙等待 | 增大 DB_CACHE_SIZE |

## 第三步：慢 SQL 识别

### 调用 `get_slow_queries` skill

```sql
-- Top SQL（按 CPU 时间排序）
SELECT sql_id, executions,
       ROUND(cpu_time/1000000, 2) cpu_sec_total,
       ROUND(elapsed_time/1000000, 2) elapsed_sec_total,
       buffer_gets, disk_reads,
       SUBSTR(sql_text, 1, 100) sql_preview
FROM v$sqlstats
WHERE executions > 0
ORDER BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;

-- ASH 近 30 分钟 Top SQL
SELECT sql_id, COUNT(*) ash_samples, event, wait_class
FROM v$active_session_history
WHERE sample_time > SYSDATE - 30/1440
  AND session_type = 'FOREGROUND'
GROUP BY sql_id, event, wait_class
ORDER BY ash_samples DESC
FETCH FIRST 20 ROWS ONLY;
```

## 第四步：空间使用检查

### 调用 `get_db_size` skill

```sql
-- 表空间使用率
SELECT t.tablespace_name,
       ROUND(t.bytes/1024/1024/1024, 2) total_gb,
       ROUND((t.bytes - NVL(f.free_bytes,0))/1024/1024/1024, 2) used_gb,
       ROUND((t.bytes - NVL(f.free_bytes,0))/t.bytes*100, 1) pct_used
FROM (
    SELECT tablespace_name, SUM(bytes) bytes FROM dba_data_files
    GROUP BY tablespace_name
) t
LEFT JOIN (
    SELECT tablespace_name, SUM(bytes) free_bytes FROM dba_free_space
    GROUP BY tablespace_name
) f ON t.tablespace_name = f.tablespace_name
ORDER BY pct_used DESC NULLS LAST;
```

**告警阈值**：表空间使用率 > 85%、归档目录使用率 > 80% 需立即处理。

## 第五步：主机资源检查

### 调用 `get_os_metrics` skill（需配置 host）

- CPU 使用率 > 80% 持续 5 分钟 → 进入 CPU 高诊断流程
- 内存使用率 > 90%，且 Swap 活跃 → 检查 SGA/PGA 配置
- IO await > 50ms → 存储性能问题
- 文件系统使用率 > 85% → 立即清理归档日志或扩容

## 第六步：Data Guard 状态

### 调用 `get_replication_status` skill

```sql
SELECT dest_id, dest_name, status, error,
       gap_status, db_unique_name
FROM v$archive_dest_status
WHERE target = 'STANDBY';

SELECT name, value, datum_time
FROM v$dataguard_stats
WHERE name IN ('apply lag', 'transport lag');
```

## 第七步：关键参数核查

### 调用 `get_db_variables` skill

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'sga_target', 'pga_aggregate_target', 'memory_target',
    'db_cache_size', 'shared_pool_size',
    'open_cursors', 'session_cached_cursors',
    'optimizer_mode', 'undo_retention', 'log_buffer'
)
ORDER BY name;
```

## 诊断结论模板

1. 健康评分（0-100）
2. 发现的问题（Critical / Warning / Info 分级）
3. 根因分析（结合 AWR/ASH 数据）
4. 优化建议（含具体 SQL 或 ALTER SYSTEM 命令）
5. 跟踪计划与复查时间节点
"""
    },
    {
        "category": "性能诊断",
        "title": "Oracle CPU使用高诊断优化流程",
        "content": r"""# Oracle CPU使用高诊断优化流程

## 概述

Oracle CPU 使用率偏高的根因通常集中在低效 SQL（全表扫描、大量硬解析）、大量并发会话、排序/哈希操作，以及 PGA 内存不足导致磁盘排序等方面。

## 诊断技能调用顺序

1. `get_os_metrics` — 确认主机 CPU 使用率（需配置 host）
2. `get_process_list` — 查找高 CPU 会话
3. `get_slow_queries` — 定位 CPU 消耗 Top SQL
4. `execute_diagnostic_query` — 分析硬解析、PGA 等细节
5. `get_db_variables` — 检查 SGA/PGA 参数配置

## 第一步：确认 CPU 高的来源

### 调用 `get_os_metrics` skill

确认是 Oracle 进程消耗 CPU 还是其他进程，Linux 下配合 `top`、`pidstat` 辅助定位。

```sql
-- 查找高 CPU 消耗的 Oracle 会话
SELECT p.spid os_pid, s.sid, s.serial#, s.username,
       s.sql_id, s.event, s.status,
       p.pga_used_mem/1024/1024 pga_mb
FROM v$process p
JOIN v$session s ON p.addr = s.paddr
WHERE s.status = 'ACTIVE'
  AND s.username IS NOT NULL
ORDER BY p.pga_used_mem DESC;
```

## 第二步：Top SQL CPU 分析

### 调用 `get_slow_queries` skill

```sql
-- v$sqlstats 按 CPU 时间排序
SELECT sql_id, plan_hash_value, executions,
       ROUND(cpu_time/1000000, 2) cpu_sec_total,
       ROUND(cpu_time/GREATEST(executions,1)/1000000, 4) cpu_sec_avg,
       buffer_gets, disk_reads, rows_processed,
       SUBSTR(sql_text, 1, 120) sql_preview
FROM v$sqlstats
WHERE executions > 0
ORDER BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;

-- ASH 近 1 小时 CPU 消耗分布
SELECT sql_id, COUNT(*) samples,
       ROUND(COUNT(*)*100/SUM(COUNT(*)) OVER(), 1) pct
FROM v$active_session_history
WHERE sample_time > SYSDATE - 1/24
  AND session_state = 'ON CPU'
  AND session_type = 'FOREGROUND'
GROUP BY sql_id
ORDER BY samples DESC
FETCH FIRST 10 ROWS ONLY;
```

## 第三步：硬解析分析

### 调用 `execute_diagnostic_query` skill

大量硬解析会导致 CPU 飙升和 Library Cache 争用。

```sql
-- 检查解析统计
SELECT name, value
FROM v$sysstat
WHERE name IN ('parse count (total)', 'parse count (hard)',
               'parse count (failures)', 'execute count');

-- 找出高硬解析 SQL
SELECT sql_id, parse_calls, executions,
       ROUND(parse_calls/GREATEST(executions,1)*100, 1) parse_pct,
       SUBSTR(sql_text, 1, 100) sql_preview
FROM v$sqlstats
WHERE parse_calls > 100
  AND parse_calls > executions * 0.5
ORDER BY parse_calls DESC
FETCH FIRST 20 ROWS ONLY;
```

**硬解析率 = hard / total，正常应 < 1%。**

常见原因：
- SQL 未使用绑定变量（每次传入不同字面值）
- `CURSOR_SHARING` 参数为 EXACT（默认），可临时设为 FORCE
- `open_cursors` 不足导致游标被频繁关闭重开

## 第四步：排序与 PGA 分析

```sql
-- PGA 使用情况
SELECT name, value/1024/1024 mb
FROM v$pgastat
WHERE name IN ('total PGA inuse', 'total PGA allocated',
               'cache hit percentage', 'aggregate PGA target parameter');

-- 磁盘排序统计
SELECT name, value
FROM v$sysstat
WHERE name IN ('sorts (memory)', 'sorts (disk)', 'sorts (rows)');
```

**cache hit percentage < 85% 说明 PGA 不足，建议增大 `pga_aggregate_target`。**

## 第五步：并行查询 CPU 消耗

```sql
-- 检查正在运行的并行查询
SELECT qc_session_id, COUNT(*) slaves, SUM(cpu_time)/1000000 cpu_sec
FROM v$px_session
GROUP BY qc_session_id
HAVING COUNT(*) > 4
ORDER BY cpu_sec DESC;
```

## 优化建议汇总

| 问题根因 | 优化措施 |
|---|---|
| 低效全表扫描 SQL | 添加合适索引，重写 SQL，调用 `explain_query` 验证执行计划 |
| 大量硬解析 | 使用绑定变量，设置 `cursor_sharing=FORCE`（临时） |
| PGA 不足/磁盘排序 | 增大 `pga_aggregate_target` |
| 过多并行进程 | 限制 `parallel_max_servers`，使用 `/*+ NO_PARALLEL */` |
| 递归 SQL 多 | 检查 dictionary cache 命中率，调整 `shared_pool_size`"""
    },
    {
        "category": "性能诊断",
        "title": "Oracle 空间占用高诊断优化流程",
        "content": r"""# Oracle 空间占用高诊断优化流程

## 概述

Oracle 空间问题涉及表空间、段、临时空间、Undo 表空间和归档日志等多个层面。空间告警如不及时处理，会导致 ORA-01653（无法扩展段）、ORA-30036（Undo 段不可扩展）等严重错误，直接影响业务连续性。

## 诊断技能调用顺序

1. `get_db_size` — 表空间整体使用率
2. `execute_diagnostic_query` — 段级别空间分析
3. `get_os_metrics` — 文件系统磁盘剩余（需配置 host）
4. `get_db_variables` — Undo/临时表空间参数

## 第一步：表空间整体扫描

### 调用 `get_db_size` skill

```sql
-- 永久表空间使用率
SELECT t.tablespace_name, t.contents, t.status,
       ROUND(d.total_mb, 0) total_mb,
       ROUND(d.total_mb - NVL(f.free_mb,0), 0) used_mb,
       ROUND((d.total_mb - NVL(f.free_mb,0))/d.total_mb*100, 1) pct_used,
       DECODE(t.autoextensible, 'YES', 'Y', 'N') autoext
FROM dba_tablespaces t
JOIN (
    SELECT tablespace_name, SUM(bytes)/1024/1024 total_mb,
           MAX(autoextensible) autoextensible
    FROM dba_data_files GROUP BY tablespace_name
) d ON t.tablespace_name = d.tablespace_name
LEFT JOIN (
    SELECT tablespace_name, SUM(bytes)/1024/1024 free_mb
    FROM dba_free_space GROUP BY tablespace_name
) f ON t.tablespace_name = f.tablespace_name
ORDER BY pct_used DESC NULLS LAST;

-- 临时表空间使用
SELECT t.tablespace_name, t.contents,
       ROUND(SUM(d.bytes)/1024/1024/1024, 2) total_gb,
       ROUND(SUM(NVL(u.blocks,0)*t.block_size)/1024/1024/1024, 2) used_gb
FROM dba_tablespaces t
JOIN dba_temp_files d ON t.tablespace_name = d.tablespace_name
LEFT JOIN v$sort_usage u ON t.tablespace_name = u.tablespace
WHERE t.contents = 'TEMPORARY'
GROUP BY t.tablespace_name, t.contents, t.block_size;
```

## 第二步：Top 大表/大段分析

### 调用 `execute_diagnostic_query` skill

```sql
-- Top 10 大段
SELECT owner, segment_name, segment_type,
       ROUND(bytes/1024/1024/1024, 2) size_gb,
       tablespace_name
FROM dba_segments
ORDER BY bytes DESC
FETCH FIRST 10 ROWS ONLY;

-- 表的实际行数与段大小对比（检测膨胀）
SELECT s.owner, s.segment_name,
       ROUND(s.bytes/1024/1024, 0) seg_mb,
       t.num_rows,
       ROUND(s.bytes/GREATEST(t.num_rows,1)/1024, 2) bytes_per_row_kb
FROM dba_segments s
JOIN dba_tables t ON s.owner = t.owner AND s.segment_name = t.table_name
WHERE s.segment_type = 'TABLE'
  AND s.bytes > 100*1024*1024
ORDER BY seg_mb DESC
FETCH FIRST 20 ROWS ONLY;
```

## 第三步：Undo 表空间分析

```sql
-- Undo 使用状态
SELECT usn, xacts, rssize/1024/1024 rss_mb, writes,
       status, name
FROM v$rollstat r
JOIN v$rollname n ON r.usn = n.usn;

-- Undo 保留与过期
SELECT status, COUNT(*), SUM(blocks)*8/1024 mb
FROM dba_undo_extents
GROUP BY status;
```

**Undo 问题常见原因**：长事务（超过 undo_retention）、Undo 表空间过小、大批量 DML 未及时提交。

## 第四步：归档日志空间

```sql
-- FRA（快速恢复区）使用
SELECT space_limit/1024/1024/1024 limit_gb,
       space_used/1024/1024/1024 used_gb,
       ROUND(space_used/space_limit*100,1) pct_used,
       space_reclaimable/1024/1024/1024 reclaimable_gb
FROM v$recovery_file_dest;

-- 近 7 天归档日志生成量
SELECT TRUNC(first_time,'DD') log_date,
       COUNT(*) log_cnt,
       ROUND(SUM(blocks*block_size)/1024/1024/1024, 2) size_gb
FROM v$archived_log
WHERE first_time > SYSDATE - 7
  AND standby_dest = 'NO'
GROUP BY TRUNC(first_time,'DD')
ORDER BY 1;
```

## 优化措施

| 问题 | 处理方法 |
|---|---|
| 表空间使用率 > 85% | ALTER TABLESPACE ... ADD DATAFILE / RESIZE |
| 大表数据碎片 | SHRINK SPACE 或 MOVE + REBUILD INDEX |
| 临时表空间满 | 检查长时间运行的排序操作，终止异常 session |
| FRA 满 | RMAN 删除过期归档：DELETE ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-3' |
| Undo 不足 | 增大 Undo 表空间，增加 undo_retention |
"""
    },
    {
        "category": "性能诊断",
        "title": "Oracle 网络流量高诊断优化流程",
        "content": r"""# Oracle 网络流量高诊断优化流程

## 概述

Oracle 数据库网络流量高通常表现为 SQL*Net 相关等待事件增多、客户端响应时间变长、网络带宽接近饱和。常见原因包括：大结果集未分页传输、频繁小包通信（chatty 应用）、LOB 数据全量传输、RAC 互联流量过高等。

## 诊断技能调用顺序

1. `get_os_metrics` — 确认主机网络接口流量（需配置 host）
2. `get_process_list` — 查找高网络等待会话
3. `execute_diagnostic_query` — 分析 SQL*Net 等待统计
4. `get_slow_queries` — 定位大结果集 SQL
5. `get_db_variables` — 检查 SDU/TDU 参数配置

## 第一步：确认网络流量来源

### 调用 `get_os_metrics` skill

在操作系统层面确认网络接口流量，识别是数据库网卡还是 RAC 心跳/互联网卡带宽饱和。

```sql
-- 查看 SQL*Net 相关等待事件
SELECT event, wait_class, total_waits, time_waited,
       ROUND(time_waited/GREATEST(total_waits,1), 2) avg_ms
FROM v$system_event
WHERE event LIKE '%SQL*Net%'
ORDER BY time_waited DESC;

-- 当前有 SQL*Net 等待的会话
SELECT s.sid, s.serial#, s.username, s.event,
       s.seconds_in_wait, s.sql_id, s.machine
FROM v$session s
WHERE s.event LIKE '%SQL*Net%'
  AND s.status = 'ACTIVE'
ORDER BY s.seconds_in_wait DESC;
```

## 第二步：网络相关等待详细分析

### 调用 `execute_diagnostic_query` skill

```sql
-- 网络 IO 统计
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'bytes sent via SQL*Net to client',
    'bytes received via SQL*Net from client',
    'bytes sent via SQL*Net to dblink',
    'bytes received via SQL*Net from dblink',
    'SQL*Net roundtrips to/from client'
);

-- 计算每次往返数据量（roundtrip 效率）
-- 理想情况下每次 roundtrip 传输数据量尽量大
```

## 第三步：大结果集 SQL 定位

### 调用 `get_slow_queries` skill

```sql
-- 按 rows_processed 排序，找出返回大量数据的 SQL
SELECT sql_id, executions, rows_processed,
       ROUND(rows_processed/GREATEST(executions,1)) rows_per_exec,
       ROUND(buffer_gets/GREATEST(executions,1)) bg_per_exec,
       SUBSTR(sql_text, 1, 100) sql_preview
FROM v$sqlstats
WHERE executions > 0
  AND rows_processed > 10000
ORDER BY rows_processed DESC
FETCH FIRST 20 ROWS ONLY;
```

**大结果集处理建议**：
- 在 SQL 层添加 `ROWNUM`/`FETCH FIRST n ROWS ONLY` 分页
- 使用游标分批拉取，避免单次全量传输
- 考虑在应用层缓存静态查询结果

## 第四步：RAC 互联流量（如适用）

```sql
-- RAC 互联（Cache Fusion）流量
SELECT inst_id, name, value/1024/1024 mb
FROM gv$sysstat
WHERE name IN (
    'gc cr blocks received', 'gc current blocks received',
    'gc cr blocks served', 'gc current blocks served'
)
ORDER BY inst_id, name;

-- 全局缓存等待事件
SELECT inst_id, event, total_waits, time_waited
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY time_waited DESC;
```

**RAC 互联流量高处理**：优化 SQL 使其尽量访问本节点数据（分区亲和性），检查互联网络带宽与延迟（正常 < 1ms）。

## 第五步：SDU/TDU 参数优化

### 调用 `get_db_variables` skill

```sql
-- 查看 tnsnames.ora 的 SDU 配置（通过 listener 参数间接查）
SELECT name, value
FROM v$parameter
WHERE name IN ('sdu', 'enable_goldengate_replication',
               'db_link_packet_size');
```

在 `sqlnet.ora` 中设置 `DEFAULT_SDU_SIZE=65535`（最大 2MB），`tnsnames.ora` 连接串中增加 `SDU=32767`，可显著减少小包数量。

## 优化建议汇总

| 问题 | 处理方法 |
|---|---|
| SQL 返回大结果集 | 添加分页，使用 Array Fetch 批量获取 |
| 大量小包往返 | 增大 SDU/TDU 参数，启用连接池 |
| DBLink 流量高 | 将处理逻辑推到远端，减少数据传输量 |
| RAC 互联饱和 | 使用分区亲和路由，升级互联网络带宽 |
| LOB 全量传输 | 使用 DBMS_LOB 分段读取，或改用 SecureFiles |
"""
    },
    {
        "category": "性能诊断",
        "title": "Oracle SQL诊断优化流程",
        "content": r"""# Oracle SQL诊断优化流程

## 概述

SQL 性能问题是 Oracle 数据库最常见的性能瓶颈来源。优化 SQL 需要结合执行计划分析、统计信息状态、绑定变量窥视、自适应游标共享等多个维度。本文档提供完整的 SQL 诊断与优化流程。

## 诊断技能调用顺序

1. `get_slow_queries` — 获取 Top 高消耗 SQL 列表
2. `explain_query` — 查看 SQL 执行计划
3. `execute_diagnostic_query` — 分析统计信息、绑定变量、Hint 使用
4. `get_table_stats` — 检查表统计信息状态
5. `get_db_variables` — 检查优化器相关参数

## 第一步：识别问题 SQL

### 调用 `get_slow_queries` skill

```sql
-- 按 elapsed time 排序
SELECT sql_id, plan_hash_value, executions,
       ROUND(elapsed_time/1000000, 2) elapsed_sec,
       ROUND(elapsed_time/GREATEST(executions,1)/1000000, 4) avg_sec,
       ROUND(cpu_time/1000000, 2) cpu_sec,
       buffer_gets, disk_reads, rows_processed,
       SUBSTR(sql_text, 1, 120) sql_preview
FROM v$sqlstats
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;

-- 查看完整 SQL 文本
SELECT sql_fulltext
FROM v$sql
WHERE sql_id = '&sql_id'
FETCH FIRST 1 ROW ONLY;
```

## 第二步：获取执行计划

### 调用 `explain_query` skill

```sql
-- 方法1：EXPLAIN PLAN
EXPLAIN PLAN FOR
SELECT * FROM orders o JOIN customers c ON o.cust_id = c.id
WHERE o.status = 'PENDING';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());

-- 方法2：从 SQL 游标缓存获取真实执行计划（推荐）
SELECT * FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR('&sql_id', NULL, 'ALLSTATS LAST +PEEKED_BINDS')
);

-- 方法3：AWR 历史执行计划
SELECT * FROM TABLE(
    DBMS_XPLAN.DISPLAY_AWR('&sql_id', &plan_hash_value)
);
```

**执行计划关键指标**：

| 操作 | 含义 | 优化方向 |
|---|---|---|
| TABLE ACCESS FULL | 全表扫描 | 检查是否缺索引，过滤条件是否有效 |
| NESTED LOOPS | 嵌套循环 | 驱动表小、被驱动表有索引时高效 |
| HASH JOIN | 哈希连接 | 大表关联时较优，需要足够 PGA |
| MERGE JOIN CARTESIAN | 笛卡尔积 | 严重问题，通常因缺少连接条件 |
| FILTER | 过滤 | 注意子查询 FILTER 可能导致多次执行 |

## 第三步：统计信息检查

### 调用 `get_table_stats` skill

```sql
-- 检查表统计信息新鲜度
SELECT owner, table_name, num_rows, blocks,
       last_analyzed,
       ROUND(SYSDATE - last_analyzed, 0) days_old,
       stale_stats
FROM dba_tab_statistics
WHERE owner = '&schema'
ORDER BY days_old DESC NULLS FIRST;

-- 列统计信息
SELECT column_name, num_distinct, num_nulls,
       low_value, high_value, histogram,
       last_analyzed
FROM dba_tab_col_statistics
WHERE owner = '&schema'
  AND table_name = '&table_name'
ORDER BY column_name;

-- 索引统计信息
SELECT index_name, num_rows, distinct_keys,
       blevel, leaf_blocks, clustering_factor,
       last_analyzed
FROM dba_ind_statistics
WHERE owner = '&schema'
  AND table_name = '&table_name';
```

**统计信息过旧（> 7 天）或 stale_stats = 'YES' 需立即收集**：

```sql
EXEC DBMS_STATS.GATHER_TABLE_STATS(
    ownname => '&schema',
    tabname => '&table_name',
    cascade => TRUE,
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
);
```

## 第四步：绑定变量窥视与自适应游标共享

### 调用 `execute_diagnostic_query` skill

```sql
-- 检查绑定变量窥视是否导致计划不稳定
SELECT sql_id, plan_hash_value, executions,
       ROUND(elapsed_time/1000000, 2) elapsed_sec,
       is_bind_sensitive, is_bind_aware, is_shareable
FROM v$sql
WHERE sql_id = '&sql_id'
ORDER BY plan_hash_value;
```

**is_bind_sensitive = 'Y' 且多个 plan_hash_value** 表示 ACS（自适应游标共享）已介入，通常是正常行为；如计划频繁切换可考虑 SQL Plan Baseline 固定。

## 第五步：SQL Plan Management（执行计划固定）

```sql
-- 创建 SQL Plan Baseline
DECLARE
  l_plans  PLS_INTEGER;
BEGIN
  l_plans := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
      sql_id => '&sql_id',
      plan_hash_value => &good_plan_hash_value
  );
  DBMS_OUTPUT.PUT_LINE('Plans loaded: ' || l_plans);
END;
/

-- 查看 SQL Plan Baselines
SELECT sql_handle, plan_name, enabled, accepted,
       fixed, executions, elapsed_time
FROM dba_sql_plan_baselines
WHERE sql_text LIKE '%&keyword%';
```

## 优化建议汇总

| 问题 | 处理方法 |
|---|---|
| 全表扫描 | 创建合适索引，或确认过滤性不足时接受全表扫描 |
| 统计信息陈旧 | DBMS_STATS 重新收集，考虑增量统计 |
| 执行计划不稳定 | 使用 SQL Plan Baseline 固定优质计划 |
| 低效 SQL | 添加 Hint（INDEX、USE_NL、LEADING）或重写 SQL |
| 绑定变量缺失 | 应用改造使用绑定变量，或设置 cursor_sharing=FORCE |
"""
    },
    {
        "category": "性能诊断",
        "title": "Oracle 写入慢诊断优化流程",
        "content": r"""# Oracle 写入慢诊断优化流程

## 概述

Oracle 写入性能问题通常表现为 INSERT/UPDATE/DELETE 响应时间长、`log file sync` 等待事件突出、批量 DML 耗时过高。根因涉及 Redo Log 写入、Undo 生成、检查点（Checkpoint）频率、索引维护开销以及存储 IO 性能等多个层面。

## 诊断技能调用顺序

1. `get_process_list` — 查找写入等待会话
2. `execute_diagnostic_query` — 分析 Redo/Undo/Checkpoint 统计
3. `get_os_metrics` — 确认磁盘 IO 性能（需配置 host）
4. `get_db_variables` — 检查 log_buffer、undo_retention 等参数
5. `get_slow_queries` — 定位高写入消耗 SQL

## 第一步：识别写入等待事件

### 调用 `get_process_list` skill

```sql
-- 与写入相关的等待事件
SELECT s.sid, s.serial#, s.username, s.event,
       s.wait_class, s.seconds_in_wait, s.sql_id
FROM v$session s
WHERE s.status = 'ACTIVE'
  AND s.wait_class NOT IN ('Idle', 'Network')
  AND s.event IN (
      'log file sync', 'log file parallel write',
      'db file parallel write', 'write complete waits',
      'checkpoint completed', 'log buffer space'
  )
ORDER BY s.seconds_in_wait DESC;

-- 系统级写入等待统计
SELECT event, total_waits, time_waited,
       ROUND(time_waited/GREATEST(total_waits,1),2) avg_ms
FROM v$system_event
WHERE event IN (
    'log file sync', 'log file parallel write',
    'db file parallel write', 'log buffer space',
    'checkpoint completed'
)
ORDER BY time_waited DESC;
```

**关键等待事件含义**：

| 等待事件 | 说明 | 处理方向 |
|---|---|---|
| log file sync | COMMIT 等待 LGWR 写日志完成 | 合并提交、优化 Redo IO |
| log buffer space | 日志缓冲区满 | 增大 log_buffer |
| db file parallel write | DBWR 写脏数据块 | 增加 DBWR 进程数，优化 IO |
| checkpoint completed | 检查点太频繁 | 增大 log file size |

## 第二步：Redo Log 分析

### 调用 `execute_diagnostic_query` skill

```sql
-- Redo Log 切换频率（每小时切换次数过多意味着日志文件太小）
SELECT TO_CHAR(first_time,'YYYY-MM-DD HH24') log_hour,
       COUNT(*) switches
FROM v$log_history
WHERE first_time > SYSDATE - 1
GROUP BY TO_CHAR(first_time,'YYYY-MM-DD HH24')
ORDER BY 1;

-- 当前 Redo Log 组状态
SELECT l.group#, l.members, l.bytes/1024/1024 size_mb,
       l.status, l.archived, lf.member
FROM v$log l
JOIN v$logfile lf ON l.group# = lf.group#
ORDER BY l.group#;

-- Redo 生成速率（字节/秒）
SELECT name, value
FROM v$sysstat
WHERE name IN ('redo size', 'redo writes', 'redo write time',
               'redo blocks written', 'redo log space requests');
```

**最佳实践**：Redo Log 切换间隔应在 15~30 分钟，若每小时切换 > 4 次，建议增大日志文件大小（推荐 500MB~2GB）。

## 第三步：DBWR 与检查点

```sql
-- DBWR 写统计
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'physical writes', 'physical writes direct',
    'background checkpoints completed',
    'background checkpoints started'
);

-- 增加 DBWR 进程数（在线修改，RAC 可能需要重启）
-- ALTER SYSTEM SET db_writer_processes = 4;
```

## 第四步：Undo 生成量

```sql
-- 大事务 Undo 消耗
SELECT t.inst_id, t.addr, t.xidusn, t.xidslot,
       t.used_ublk * 8 / 1024 undo_mb,
       t.used_urec undo_records,
       s.username, s.sql_id
FROM gv$transaction t
JOIN gv$session s ON t.ses_addr = s.saddr AND t.inst_id = s.inst_id
ORDER BY t.used_ublk DESC
FETCH FIRST 10 ROWS ONLY;
```

## 第五步：批量写入优化建议

```sql
-- 使用 APPEND Hint 直接路径插入（绕过 Buffer Cache）
INSERT /*+ APPEND */ INTO target_table
SELECT * FROM source_table;
COMMIT;

-- 禁用/延迟索引维护（批量导入期间）
ALTER INDEX idx_name UNUSABLE;
-- ... 批量导入 ...
ALTER INDEX idx_name REBUILD NOLOGGING PARALLEL 4;

-- NOLOGGING 模式减少 Redo 生成（非归档或 Data Guard 同步注意）
ALTER TABLE t NOLOGGING;
INSERT /*+ APPEND */ INTO t ...
ALTER TABLE t LOGGING;
```

## 优化建议汇总

| 问题 | 处理方法 |
|---|---|
| log file sync 高 | 合并小事务批量提交，将 Redo 日志移至 SSD |
| log buffer space | ALTER SYSTEM SET log_buffer = 64M |
| Redo Log 切换频繁 | 增大 Redo Log 文件尺寸至 1GB 以上 |
| 批量插入慢 | 使用 APPEND Hint + NOLOGGING，禁用索引后重建 |
| Undo 空间不足 | 增大 Undo 表空间，增加 undo_retention 时间 |
"""
    },
    {
        "category": "性能诊断",
        "title": "Oracle 索引优化诊断流程",
        "content": r"""# Oracle 索引优化诊断流程

## 概述

Oracle 索引优化包括识别缺失索引、无效索引、冗余索引、索引碎片以及不合理索引类型（B-Tree vs 位图 vs 函数索引）。索引过多会拖慢写入性能；索引不足或选择性差会导致全表扫描。

## 诊断技能调用顺序

1. `get_table_stats` — 检查表与索引统计信息
2. `execute_diagnostic_query` — 分析索引使用率与碎片
3. `explain_query` — 验证 SQL 是否使用了期望的索引
4. `get_slow_queries` — 识别因索引问题导致的慢 SQL

## 第一步：索引使用率监控

### 调用 `execute_diagnostic_query` skill

```sql
-- 开启索引使用监控（12c 以下需手动开启）
ALTER INDEX idx_name MONITORING USAGE;

-- 查看索引使用情况（v$object_usage）
SELECT index_name, table_name, monitoring,
       used, start_monitoring, end_monitoring
FROM v$object_usage
ORDER BY used, table_name;

-- 12c+ 通过 v$index_usage_info
SELECT i.owner, i.index_name, i.table_name,
       u.total_access_count, u.total_exec_count,
       u.last_used
FROM dba_indexes i
LEFT JOIN v$index_usage_info u
    ON i.owner = u.object_owner
    AND i.index_name = u.name
WHERE i.owner = '&schema'
ORDER BY NVL(u.total_access_count, 0);
```

## 第二步：索引碎片检查

```sql
-- 索引碎片分析（使用 ANALYZE)
ANALYZE INDEX idx_name VALIDATE STRUCTURE;

SELECT name, height, blocks, lf_rows, lf_blks,
       del_lf_rows,
       ROUND(del_lf_rows/GREATEST(lf_rows,1)*100, 1) del_pct,
       br_rows, br_blks
FROM index_stats;

-- del_pct > 20% 建议重建索引
-- height > 4 对于大索引可能需要重建

-- 索引聚簇因子
SELECT index_name, clustering_factor, num_rows,
       blevel, leaf_blocks,
       ROUND(clustering_factor/GREATEST(num_rows,1)*100, 1) cf_pct
FROM dba_ind_statistics
WHERE owner = '&schema'
  AND table_name = '&table_name'
ORDER BY clustering_factor DESC;
```

**clustering_factor 接近 num_rows** 说明索引与表存储顺序一致，IO 效率高；**接近 blocks** 说明乱序严重，大范围扫描性能差。

## 第三步：冗余索引识别

```sql
-- 查找列前缀相同的冗余索引
SELECT a.owner, a.table_name,
       a.index_name redundant_index,
       b.index_name covering_index,
       a.column_list
FROM (
    SELECT owner, index_name, table_name,
           LISTAGG(column_name, ',') WITHIN GROUP (ORDER BY column_position) column_list
    FROM dba_ind_columns
    WHERE owner = '&schema'
    GROUP BY owner, index_name, table_name
) a
JOIN (
    SELECT owner, index_name, table_name,
           LISTAGG(column_name, ',') WITHIN GROUP (ORDER BY column_position) column_list
    FROM dba_ind_columns
    WHERE owner = '&schema'
    GROUP BY owner, index_name, table_name
) b ON a.owner = b.owner
    AND a.table_name = b.table_name
    AND b.column_list LIKE a.column_list || '%'
    AND a.index_name != b.index_name;
```

## 第四步：索引重建

```sql
-- 在线重建索引（不阻塞 DML，Oracle 11g+）
ALTER INDEX idx_name REBUILD ONLINE;

-- 合并索引叶块（轻量操作，不改变高水位线）
ALTER INDEX idx_name COALESCE;

-- 批量重建指定 schema 下所有碎片化索引（示例脚本）
BEGIN
    FOR r IN (
        SELECT owner, index_name
        FROM dba_indexes
        WHERE owner = '&schema'
          AND status = 'VALID'
    ) LOOP
        EXECUTE IMMEDIATE
            'ALTER INDEX ' || r.owner || '.' || r.index_name || ' REBUILD ONLINE';
    END LOOP;
END;
/
```


## 第五步：函数索引与位图索引适用场景

```sql
-- 函数索引（适合 WHERE UPPER(col) = ...）
CREATE INDEX idx_upper_name ON customers (UPPER(last_name));

-- 位图索引（适合低基数列，OLAP/报表场景，不适合 OLTP 高并发写）
CREATE BITMAP INDEX idx_status ON orders (status);

-- 组合索引列顺序：将过滤性最高的列放最前
CREATE INDEX idx_orders_cust_status ON orders (customer_id, status, order_date);
```

## 优化建议汇总

| 问题 | 处理方法 |
|---|---|
| 缺失索引 | 根据 SQL WHERE/JOIN 条件创建合适索引 |
| 索引未被使用 | 检查 SQL 写法（函数包裹、隐式转换） |
| 索引碎片高 | REBUILD ONLINE 或 COALESCE |
| 冗余索引 | 删除被覆盖的短前缀索引，减少写入开销 |
| 聚簇因子差 | 重组表（MOVE + REBUILD INDEX）改善存储顺序 |
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle 死锁诊断优化流程",
        "content": r"""# Oracle 死锁诊断优化流程

## 概述

Oracle 死锁（Deadlock）发生时，数据库会自动检测并回滚其中一个事务（牺牲者），同时在告警日志（alert log）中记录 ORA-00060 错误，并在 trace 文件中保存死锁图。死锁本身不会导致数据库宕机，但频繁死锁会影响业务逻辑正确性，需要从应用层根治。

## 诊断技能调用顺序

1. `get_process_list` — 查看当前锁等待情况
2. `execute_diagnostic_query` — 分析锁等待链与 V$LOCK
3. `get_db_status` — 检查告警日志中的 ORA-00060

## 第一步：确认死锁发生

### 调用 `get_db_status` skill

```sql
-- 查看 Oracle 告警日志（通过 v$diag_alert_ext，12c+）
SELECT originating_timestamp, message_text
FROM v$diag_alert_ext
WHERE message_text LIKE '%ORA-00060%'
  AND originating_timestamp > SYSDATE - 1
ORDER BY originating_timestamp DESC;
```

死锁发生后，trace 文件路径可通过以下 SQL 获取：
```sql
SELECT value FROM v$diag_info WHERE name = 'Default Trace File';
```

## 第二步：当前锁等待分析

### 调用 `get_process_list` skill

```sql
-- 当前锁等待会话
SELECT s.sid, s.serial#, s.username, s.status,
       s.event, s.seconds_in_wait, s.blocking_session,
       s.sql_id, s.machine
FROM v$session s
WHERE s.blocking_session IS NOT NULL
ORDER BY s.seconds_in_wait DESC;

-- 锁等待链（递归查找阻塞链）
SELECT LEVEL, s.sid, s.serial#, s.username,
       s.blocking_session blocker, s.event,
       s.seconds_in_wait, s.sql_id
FROM v$session s
START WITH s.blocking_session IS NULL
       AND s.sid IN (SELECT blocking_session FROM v$session WHERE blocking_session IS NOT NULL)
CONNECT BY PRIOR s.sid = s.blocking_session
ORDER SIBLINGS BY s.seconds_in_wait DESC;
```

## 第三步：V$LOCK 详细分析

### 调用 `execute_diagnostic_query` skill

```sql
-- 查看锁类型与阻塞关系
SELECT l1.sid waiter, l2.sid holder,
       l1.type lock_type, l1.id1, l1.id2,
       l1.request req_mode, l2.lmode held_mode
FROM v$lock l1
JOIN v$lock l2 ON l1.id1 = l2.id1 AND l1.id2 = l2.id2
WHERE l1.request > 0
  AND l2.lmode > 0
  AND l1.sid != l2.sid;

-- 找出被锁定的对象
SELECT lo.oracle_username, lo.os_user_name,
       do.object_name, do.object_type,
       lo.locked_mode
FROM v$locked_object lo
JOIN dba_objects do ON lo.object_id = do.object_id;
```

**锁模式说明**：

| lmode | 含义 |
|---|---|
| 0 | None |
| 1 | Null |
| 2 | Row Share (SS) |
| 3 | Row Exclusive (SX) |
| 4 | Share (S) |
| 5 | Share Row Exclusive (SSX) |
| 6 | Exclusive (X) |

## 第四步：终止阻塞会话

```sql
-- 查找阻塞会话的 SID 和 SERIAL#
SELECT sid, serial#, username, status, event
FROM v$session
WHERE sid = &blocking_sid;

-- 终止会话
ALTER SYSTEM KILL SESSION '&sid,&serial#' IMMEDIATE;
```

**注意**：终止会话前确认业务影响，优先与应用团队沟通。

## 第五步：根因分析与预防

**常见死锁模式**：

1. **双向更新死锁**：事务 A 更新行 1→行 2，事务 B 更新行 2→行 1，形成循环等待
2. **主外键无索引**：子表外键列未建索引，删除父表行时锁定子表全表
3. **大批量更新未分段**：长事务持锁时间过长

**预防措施**：

```sql
-- 检查外键是否缺失索引（常见死锁根因）
SELECT c.owner, c.table_name, c.constraint_name,
       c.r_constraint_name
FROM dba_constraints c
WHERE c.constraint_type = 'R'
  AND c.owner = '&schema'
  AND NOT EXISTS (
      SELECT 1 FROM dba_ind_columns ic
      WHERE ic.table_name = c.table_name
        AND ic.owner = c.owner
        AND ic.column_name IN (
            SELECT cc.column_name FROM dba_cons_columns cc
            WHERE cc.constraint_name = c.constraint_name
              AND cc.owner = c.owner
        )
  );

-- 为外键添加索引
CREATE INDEX idx_fk_col ON child_table (fk_column);
```

## 优化建议

| 根因 | 解决方案 |
|---|---|
| 事务顺序不一致 | 应用层统一 DML 顺序，按主键升序操作 |
| 外键无索引 | 为所有外键列创建索引 |
| 大事务持锁 | 拆分批量 DML，小批量多次提交 |
| SELECT FOR UPDATE 滥用 | 评估业务是否真正需要悲观锁 |
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle 连接失败诊断流程",
        "content": r"""# Oracle 连接失败诊断流程

## 概述

Oracle 连接失败常见错误包括 ORA-12541（TNS 无监听）、ORA-01017（用户名/密码错误）、ORA-12519（TNS 无可用处理程序）、ORA-00018（超出最大会话数）、ORA-12170（连接超时）等。本文档提供系统化诊断步骤。

## 诊断技能调用顺序

1. `get_db_status` — 确认实例状态与监听状态
2. `execute_diagnostic_query` — 检查会话数与连接池
3. `get_db_variables` — 检查 processes/sessions 参数
4. `get_os_metrics` — 检查主机资源（需配置 host）

## 常见错误码对照

| ORA 错误码 | 含义 | 初步处理方向 |
|---|---|---|
| ORA-12541 | TNS: 无监听程序 | 检查监听是否启动 |
| ORA-12514 | TNS: 监听不知道服务名 | 检查 tnsnames.ora 和 listener.ora |
| ORA-12519 | TNS: 无可用处理程序 | 连接数达到 PROCESSES 上限 |
| ORA-00018 | 超出最大会话数 | SESSIONS 参数不足 |
| ORA-01017 | 用户名/密码无效 | 检查认证信息 |
| ORA-28000 | 账户被锁定 | FAILED_LOGIN_ATTEMPTS 触发 |
| ORA-12170 | 连接超时 | 网络问题或服务器负载高 |
| ORA-28001 | 密码已过期 | 修改密码或调整 PASSWORD_LIFE_TIME |

## 第一步：确认监听与实例状态

### 调用 `get_db_status` skill

```sql
-- 实例状态
SELECT instance_name, status, database_status
FROM v$instance;

-- 注册到监听的服务
SELECT name, network_name, creation_date
FROM v$services
ORDER BY name;

-- 监听状态（OS 命令）
-- lsnrctl status
-- lsnrctl services
```

## 第二步：会话数检查

### 调用 `execute_diagnostic_query` skill

```sql
-- 当前会话数与 PROCESSES 限制
SELECT 'Current Sessions' metric,
       COUNT(*) current_val,
       (SELECT value FROM v$parameter WHERE name='sessions') max_val
FROM v$session
UNION ALL
SELECT 'Active Sessions',
       COUNT(*),
       (SELECT value FROM v$parameter WHERE name='sessions')
FROM v$session WHERE status = 'ACTIVE'
UNION ALL
SELECT 'Processes',
       COUNT(*),
       (SELECT value FROM v$parameter WHERE name='processes')
FROM v$process;

-- 按应用/机器统计连接
SELECT machine, program, username,
       COUNT(*) sessions,
       SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) active
FROM v$session
WHERE username IS NOT NULL
GROUP BY machine, program, username
ORDER BY sessions DESC;
```

## 第三步：账户锁定检查

```sql
-- 检查用户账户状态
SELECT username, account_status, lock_date,
       expiry_date, profile
FROM dba_user
WHERE account_status != 'OPEN'
ORDER BY account_status;

-- 解锁账户
ALTER USER username ACCOUNT UNLOCK;

-- 重置密码
ALTER USER username IDENTIFIED BY new_password;

-- 检查 Profile 密码策略
SELECT profile, resource_name, limit
FROM dba_profiles
WHERE resource_name IN (
    'FAILED_LOGIN_ATTEMPTS', 'PASSWORD_LIFE_TIME',
    'PASSWORD_LOCK_TIME', 'PASSWORD_GRACE_TIME'
)
ORDER BY profile, resource_name;
```

## 第四步：PROCESSES 参数调整

### 调用 `get_db_variables` skill

```sql
SELECT name, value, description
FROM v$parameter
WHERE name IN ('processes', 'sessions',
               'open_cursors', 'session_cached_cursors');
```

**SESSIONS = CEIL(PROCESSES * 1.1) + 5**（Oracle 自动计算，调整 PROCESSES 即可）

```sql
-- 增大 PROCESSES（需重启数据库）
ALTER SYSTEM SET processes = 500 SCOPE=SPFILE;
-- SHUTDOWN IMMEDIATE; STARTUP;
```

## 第五步：连接池配置检查

生产环境应使用连接池（DRCP 或应用层连接池）避免频繁建立连接：

```sql
-- 检查 DRCP 状态（Database Resident Connection Pool）
SELECT connection_pool, status, minsize, maxsize,
       num_open_servers, num_busy_servers
FROM v$cpool_stats;

-- 启用 DRCP
EXEC DBMS_CONNECTION_POOL.START_POOL();
```

## 优化建议

| 问题 | 处理方法 |
|---|---|
| PROCESSES 耗尽 | 增大 processes 参数，使用连接池 |
| 账户锁定 | 解锁账户，调整 FAILED_LOGIN_ATTEMPTS |
| 密码过期 | 修改密码，设置 PASSWORD_LIFE_TIME=UNLIMITED |
| 监听未启动 | lsnrctl start，检查 listener.ora 配置 |
| 连接超时 | 检查网络、防火墙、sqlnet.ora SQLNET.EXPIRE_TIME |
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle SQL执行失败诊断流程",
        "content": r"""# Oracle SQL执行失败诊断流程

## 概述

Oracle SQL 执行失败涵盖多种错误类型：ORA-00942（表不存在）、ORA-01403（未找到数据）、ORA-01555（快照太旧）、ORA-04031（共享池不足）、ORA-04030（PGA 内存不足）、ORA-12899（列值过大）等。诊断需结合错误码、执行上下文和数据库状态综合分析。

## 诊断技能调用顺序

1. `execute_diagnostic_query` — 重现错误，查询错误上下文
2. `get_db_status` — 检查实例告警日志
3. `get_db_variables` — 检查相关参数（undo_retention、shared_pool_size）
4. `explain_query` — 分析失败 SQL 执行计划

## 常见错误码诊断

### ORA-01555：快照太旧（Snapshot Too Old）

**现象**：长时间运行的查询遭遇 Undo 被覆盖。

```sql
-- 检查 Undo 配置
SELECT name, value FROM v$parameter
WHERE name IN ('undo_retention', 'undo_tablespace');

-- 查看 Undo 统计
SELECT tuned_undoretention, maxquerylen,
       maxconcurrency, ssolderrcnt
FROM v$undostat
ORDER BY end_time DESC
FETCH FIRST 10 ROWS ONLY;
```

**解决**：增大 `undo_retention`，扩大 Undo 表空间，或优化长查询拆分为短事务。

### ORA-04031：共享池内存不足

```sql
-- 共享池使用情况
SELECT pool, name, bytes/1024/1024 mb
FROM v$sgastat
WHERE pool = 'shared pool'
  AND bytes > 1024*1024
ORDER BY bytes DESC;

-- 检查大型 SQL 占用共享池
SELECT sql_id, sharable_mem/1024/1024 mem_mb,
       executions, loads,
       SUBSTR(sql_text, 1, 80) sql_preview
FROM v$sql
WHERE sharable_mem > 10*1024*1024
ORDER BY sharable_mem DESC;

-- 刷新共享池（谨慎操作，影响性能）
-- ALTER SYSTEM FLUSH SHARED_POOL;
```

### ORA-01653 / ORA-01654：无法分配 Extent

```sql
-- 找到空间不足的表空间
SELECT tablespace_name, file_name,
       bytes/1024/1024 total_mb,
       maxbytes/1024/1024 max_mb,
       autoextensible
FROM dba_data_files
WHERE tablespace_name IN (
    SELECT tablespace_name FROM dba_free_space
    GROUP BY tablespace_name
    HAVING SUM(bytes) < 10*1024*1024
);

-- 扩展数据文件
ALTER DATABASE DATAFILE '/path/to/datafile.dbf' RESIZE 10G;
-- 或添加新数据文件
ALTER TABLESPACE user ADD DATAFILE '/path/new.dbf' SIZE 5G AUTOEXTEND ON;
```

### ORA-00942：表或视图不存在

```sql
-- 检查对象是否存在
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE object_name = UPPER('&table_name');

-- 检查同义词
SELECT synonym_name, table_owner, table_name, db_link
FROM dba_synonyms
WHERE synonym_name = UPPER('&table_name');

-- 检查权限
SELECT grantee, owner, table_name, privilege
FROM dba_tab_privs
WHERE table_name = UPPER('&table_name')
  AND grantee IN (USER, 'PUBLIC');
```

### ORA-04030：PGA 内存不足

```sql
-- PGA 使用情况
SELECT name, value/1024/1024 mb
FROM v$pgastat
WHERE name IN ('total PGA inuse', 'total PGA allocated',
               'cache hit percentage',
               'aggregate PGA target parameter');

-- 高 PGA 使用会话
SELECT s.sid, s.serial#, s.username,
       p.pga_alloc_mem/1024/1024 pga_alloc_mb,
       p.pga_max_mem/1024/1024 pga_max_mb,
       s.sql_id
FROM v$session s
JOIN v$process p ON s.paddr = p.addr
ORDER BY p.pga_alloc_mem DESC
FETCH FIRST 10 ROWS ONLY;
```

## 通用诊断流程

```sql
-- 查看最近告警日志错误
SELECT originating_timestamp, message_text
FROM v$diag_alert_ext
WHERE originating_timestamp > SYSDATE - 1/24
  AND message_level <= 2
ORDER BY originating_timestamp DESC;

-- 查看 SQL 执行错误历史
SELECT executions, parse_calls, loaded_versions,
       invalidations, loads, rows_processed,
       sql_id, SUBSTR(sql_text, 1, 100) sql_preview
FROM v$sqlstats
WHERE executions = 0 OR loaded_versions > 1
ORDER BY loads DESC
FETCH FIRST 20 ROWS ONLY;
```
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle 主备延时诊断流程（Data Guard）",
        "content": r"""# Oracle 主备延时诊断流程（Data Guard）

## 概述

Oracle Data Guard 是官方主备高可用方案，支持物理备库（Physical Standby）和逻辑备库（Logical Standby）。主备延时过高会导致 RPO（恢复点目标）增大，Failover 后数据丢失风险上升。本文档提供 Data Guard 延时诊断完整流程。

## 诊断技能调用顺序

1. `get_replication_status` — 获取 Data Guard 整体状态
2. `execute_diagnostic_query` — 分析 Apply/Transport Lag 详情
3. `get_db_status` — 检查主备库告警日志
4. `get_os_metrics` — 检查主备网络带宽与 IO（需配置 host）

## 第一步：Data Guard 整体状态

### 调用 `get_replication_status` skill

```sql
-- 主库：归档目的地状态
SELECT dest_id, dest_name, status,
       target, archiver, schedule,
       destination, error, gap_status,
       db_unique_name
FROM v$archive_dest_status
WHERE target = 'STANDBY'
  AND status != 'INACTIVE';

-- 备库：DG 延迟统计
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag',
               'apply finish time', 'estimated startup time')
ORDER BY name;
```

**关键指标**：

| 指标 | 正常值 | 告警阈值 |
|---|---|---|
| transport lag | < 5 秒 | > 30 秒 |
| apply lag | < 10 秒 | > 60 秒 |
| gap_status | NO GAP | 有 Gap 需立即处理 |

## 第二步：Redo 传输分析

### 调用 `execute_diagnostic_query` skill

```sql
-- 主库：检查归档日志传输状态
SELECT dest_id, thread#, sequence#,
       blocks, block_size,
       completion_time, next_time,
       standby_dest, applied
FROM v$archived_log
WHERE standby_dest = 'YES'
  AND completion_time > SYSDATE - 1/24
ORDER BY completion_time DESC;

-- 主库：检查是否有 Archive Gap
SELECT thread#, low_sequence#, high_sequence#
FROM v$archive_gap;

-- 备库：检查 MRP（Managed Recovery Process）状态
SELECT process, status, thread#, sequence#,
       block#, blocks
FROM v$managed_standby
WHERE process IN ('MRP0', 'RFS', 'ARCH')
ORDER BY process;
```

## 第三步：Apply 进程分析

```sql
-- 备库：Apply 进度
SELECT thread#, sequence#, block#, blocks,
       delay_mins
FROM v$managed_standby
WHERE process = 'MRP0';

-- 备库：已应用的日志与未应用的日志
SELECT thread#, MAX(sequence#) max_applied
FROM v$archived_log
WHERE applied = 'YES'
GROUP BY thread#;

SELECT thread#, MAX(sequence#) max_received
FROM v$archived_log
WHERE standby_dest = 'NO'
GROUP BY thread#;

-- Apply Lag 计算
SELECT ROUND((SYSDATE -
    (SELECT MAX(next_time) FROM v$archived_log WHERE applied='YES'))*86400) apply_lag_sec
FROM dual;
```

## 第四步：Redo Apply 参数优化

```sql
-- 检查并行 Apply 配置
SELECT name, value FROM v$parameter
WHERE name IN (
    'log_archive_dest_1', 'log_archive_dest_2',
    'log_archive_dest_state_2',
    'db_file_name_convert', 'log_file_name_convert',
    'recovery_parallelism', 'parallel_servers_target'
);

-- 增加并行 Apply 进程数
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
    USING CURRENT LOGFILE
    PARALLEL 8;
```

## 第五步：Redo Gap 修复

```sql
-- 主库：手动注册归档日志（FAL 自动获取失败时）
ALTER DATABASE REGISTER LOGFILE '/path/to/archive/1_100_xxx.arc';

-- 备库：启动 FAL（Fetch Archive Log）
ALTER SYSTEM SET fal_server = 'PRIMARY_DB';
ALTER SYSTEM SET fal_client = 'STANDBY_DB';
```

## 优化建议

| 问题 | 处理方法 |
|---|---|
| Transport Lag 高 | 检查主备网络带宽，启用压缩传输 |
| Apply Lag 高 | 增大 recovery_parallelism，使用实时日志传输 |
| Archive Gap | 检查 FAL 配置，手动注册缺失归档 |
| MRP 停止 | 重启 MRP：ALTER DATABASE RECOVER MANAGED STANDBY DATABASE DISCONNECT |
| 归档目录满 | 删除旧归档，RMAN 清理过期备份 |
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle 主备数据不一致诊断流程",
        "content": r"""# Oracle 主备数据不一致诊断流程

## 概述

Oracle Data Guard 物理备库通过 Redo Apply 保持与主库块级别一致，正常情况下数据一致性由 Oracle 内部机制保证。数据不一致通常发生在以下场景：逻辑备库（Logical Standby）的 SQL Apply 跳过了不支持的 DDL/DML；手动直接修改了备库数据；或备库 OPEN 为 READ WRITE 后又切回 Standby 模式。本文档提供不一致检测与修复方案。

## 诊断技能调用顺序

1. `get_replication_status` — 确认备库模式与保护级别
2. `execute_diagnostic_query` — 运行数据比对查询
3. `get_db_status` — 检查 Apply 错误日志

## 第一步：确认备库保护模式

### 调用 `get_replication_status` skill

```sql
-- 主库：数据库保护模式
SELECT name, db_unique_name, database_role,
       protection_mode, protection_level,
       open_mode
FROM v$database;

-- 备库：应用状态
SELECT database_role, open_mode,
       protection_mode, protection_level,
       switchover_status
FROM v$database;
```

**保护模式**：

| 模式 | 数据保护级别 | 性能影响 |
|---|---|---|
| Maximum Protection | 零数据丢失 | 主库等待备库确认 |
| Maximum Availability | 近零丢失 | 网络中断时自动降级 |
| Maximum Performance | 可能丢失部分数据 | 异步传输，性能最优 |

## 第二步：检测数据一致性

### 调用 `execute_diagnostic_query` skill

**方法1：DBVERIFY 工具（OS 层面）**
```bash
dbv file=/path/to/datafile.dbf blocksize=8192
```

**方法2：RMAN 验证块一致性**
```sql
-- 在 RMAN 中验证备库数据文件
RMAN> BACKUP VALIDATE DATABASE;
-- 检查坏块报告
SELECT file#, block#, blocks, corruption_type
FROM v$database_block_corruption;
```

**方法3：逻辑备库不一致检测**
```sql
-- 逻辑备库跳过的事务
SELECT error_number, error_message,
       scn, commit_scn, xidusn, xidslot
FROM dba_logstdby_events
WHERE event_time > SYSDATE - 1
ORDER BY event_time DESC;

-- 逻辑备库不支持的对象
SELECT owner, table_name, reason
FROM dba_logstdby_unsupported;
```

## 第三步：主备数据行级比对

```sql
-- 使用 DBMS_COMPARISON 包进行数据比对
BEGIN
    DBMS_COMPARISON.CREATE_COMPARISON(
        comparison_name => 'COMP_ORDERS',
        schema_name     => 'SCOTT',
        object_name     => 'ORDERS',
        dblink_name     => 'STANDBY_LINK'
    );
END;
/

-- 执行比对
DECLARE
    l_result BOOLEAN;
BEGIN
    l_result := DBMS_COMPARISON.COMPARE(
        comparison_name => 'COMP_ORDERS',
        scan_info       => NULL,
        perform_row_dif => TRUE
    );
    IF l_result THEN
        DBMS_OUTPUT.PUT_LINE('Tables are consistent');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Differences found!');
    END IF;
END;
/

-- 查看差异结果
SELECT scan_id, local_rowid, remote_rowid, index_value
FROM user_comparison_row_dif
WHERE comparison_name = 'COMP_ORDERS';
```

## 第四步：修复不一致

**物理备库**：如检测到数据块损坏，使用 RMAN 从主库恢复：
```sql
-- 在备库 RMAN 中执行
RMAN> RECOVER DATABASE;

-- 或修复特定数据文件
RMAN> RECOVER DATAFILE 5;
```

**逻辑备库跳过问题**：
```sql
-- 重新同步逻辑备库（INSTANTIATE 特定表）
EXEC DBMS_LOGSTDBY.INSTANTIATE_TABLE(
    schema_name => 'SCOTT',
    table_name  => 'ORDERS',
    dblink      => 'PRIMARY_LINK'
);
```

## 预防措施

1. 不要对备库直接进行 DML 操作（Active Data Guard 只读查询除外）
2. 逻辑备库避免使用 SQL Apply 不支持的数据类型（如 LONG、XMLType 的某些操作）
3. 定期使用 RMAN VALIDATE 检查备库数据文件完整性
4. 启用 Maximum Availability 或 Maximum Protection 模式保障数据一致性
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle 启动失败诊断流程",
        "content": r"""# Oracle 启动失败诊断流程

## 概述

Oracle 数据库启动分为三个阶段：NOMOUNT（读取 SPFILE/PFILE）、MOUNT（读取控制文件）、OPEN（读取数据文件/联机日志）。不同阶段失败对应不同错误码。常见错误包括 ORA-00205（控制文件错误）、ORA-01157（数据文件未找到）、ORA-27102（内存不足）等。

## 诊断技能调用顺序

1. `get_db_status` — 检查当前实例状态与告警日志
2. `execute_diagnostic_query` — 查询控制文件、数据文件状态
3. `get_os_metrics` — 检查主机内存与文件系统（需配置 host）

## 启动阶段与常见错误

| 阶段 | 读取内容 | 常见错误 |
|---|---|---|
| NOMOUNT | SPFILE/PFILE, SGA 分配 | ORA-27102（内存不足），ORA-01078（参数错误） |
| MOUNT | 控制文件 | ORA-00205（控制文件错误），ORA-00202（控制文件 IO 错误） |
| OPEN | 数据文件、Redo Log | ORA-01157（数据文件不存在），ORA-00313（Redo Log 打开错误） |

## 第一步：查看告警日志

### 调用 `get_db_status` skill

```sql
-- 获取 ADR 路径
SELECT name, value FROM v$diag_info;

-- 查看最近告警
SELECT originating_timestamp, message_text
FROM v$diag_alert_ext
WHERE originating_timestamp > SYSDATE - 1
ORDER BY originating_timestamp DESC;
```

告警日志路径：`$ORACLE_BASE/diag/rdbms/<db_name>/<instance_name>/trace/alert_<instance_name>.log`

## 第二步：NOMOUNT 阶段失败处理

**ORA-27102：内存不足（SGA 无法分配）**

```bash
free -h
grep -i hugepage /etc/sysctl.conf
```

```sql
-- 修改 PFILE 减小 SGA 后重试
STARTUP PFILE='/tmp/init_reduced.ora';
CREATE SPFILE FROM PFILE='/tmp/init_reduced.ora';
```

**ORA-01078：参数错误**

```bash
strings $ORACLE_HOME/dbs/spfile<SID>.ora > /tmp/init<SID>.ora
# 编辑修正错误参数
startup pfile='/tmp/init<SID>.ora'
```

## 第三步：MOUNT 阶段失败处理

**ORA-00205：控制文件错误**

```sql
SHOW PARAMETER control_files;

-- 从多路复用副本恢复
-- OS层: cp /u01/ctrl01.ctl /u02/ctrl02.ctl

-- 从 RMAN 备份恢复控制文件
STARTUP NOMOUNT;
RMAN> RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RMAN> RECOVER DATABASE;
ALTER DATABASE OPEN RESETLOGS;
```

## 第四步：OPEN 阶段失败处理

**ORA-01157：数据文件不存在**

```sql
SELECT file#, name, status FROM v$datafile;
SELECT file#, name, status FROM v$datafile_header;

-- 非系统数据文件：离线后打开
ALTER DATABASE DATAFILE '/u01/missing.dbf' OFFLINE DROP;
ALTER DATABASE OPEN;

-- 之后从备份恢复
RMAN> RESTORE DATAFILE 5;
RMAN> RECOVER DATAFILE 5;
ALTER DATABASE DATAFILE 5 ONLINE;
```

**ORA-00313：Redo Log 无法打开**

```sql
SELECT group#, status, archived, members FROM v$log;
SELECT group#, member, status FROM v$logfile;

-- 清除非当前日志组
ALTER DATABASE CLEAR LOGFILE GROUP 2;

-- 当前日志组（有数据丢失风险）
ALTER DATABASE CLEAR UNARCHIVED LOGFILE GROUP 2;
ALTER DATABASE OPEN RESETLOGS;
```

## 第五步：RMAN 完全恢复

```sql
STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
ALTER DATABASE OPEN;

-- 不完全恢复
RMAN> RECOVER DATABASE UNTIL TIME "TO_DATE('2026-03-20 10:00:00','YYYY-MM-DD HH24:MI:SS')";
ALTER DATABASE OPEN RESETLOGS;
```

## 预防措施

| 问题 | 预防措施 |
|---|---|
| 控制文件损坏 | 配置多路复用控制文件（至少 3 份，不同磁盘） |
| 数据文件丢失 | 定期 RMAN 备份，启用 FRA |
| 参数错误导致无法启动 | 修改前备份 SPFILE，测试环境验证 |
| SGA 分配失败 | 配置 HugePages，避免 OS 内存碎片 |
"""
    },
    {
        "category": "故障排查",
        "title": "Oracle 数据丢失恢复方案",
        "content": r"""# Oracle 数据丢失恢复方案

## 概述

Oracle 提供多种数据恢复手段，覆盖从误操作（DROP TABLE、DELETE 全表）到存储故障（数据文件损坏）等多种场景。核心工具包括：Flashback（闪回）、RMAN、LogMiner、Data Pump 导出备份。

## 诊断技能调用顺序

1. `get_db_status` — 确认数据库闪回、归档状态
2. `execute_diagnostic_query` — 查询 Undo 可恢复时间窗口
3. `get_db_variables` — 检查 db_flashback_retention_target、undo_retention

## 第一步：评估恢复方案

### 调用 `get_db_status` skill

```sql
-- 检查闪回数据库是否启用
SELECT flashback_on, log_mode, db_unique_name
FROM v$database;

-- Undo 可恢复时间窗口
SELECT MIN(begin_time), MAX(end_time),
       MAX(tuned_undoretention) undo_sec
FROM v$undostat;

-- 闪回日志覆盖范围
SELECT oldest_flashback_scn, oldest_flashback_time
FROM v$flashback_database_log;
```

## 第二步：闪回查询（行级恢复）

**适用场景**：误 DELETE/UPDATE，数据在 Undo 保留期内。

```sql
-- 查询历史时间点数据
SELECT * FROM orders
AS OF TIMESTAMP TO_TIMESTAMP('2026-03-20 09:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = 12345;

-- 恢复误删除的数据
INSERT INTO orders
SELECT * FROM orders
AS OF TIMESTAMP (SYSTIMESTAMP - INTERVAL '30' MINUTE)
WHERE order_id IN (12345, 12346);
COMMIT;
```

## 第三步：Flashback Table（表级恢复）

**适用场景**：误 DELETE 大量数据，需整表回退。

```sql
-- 前提：开启行移动
ALTER TABLE orders ENABLE ROW MOVEMENT;

-- 闪回到指定时间点
FLASHBACK TABLE orders
TO TIMESTAMP TO_TIMESTAMP('2026-03-20 08:00:00', 'YYYY-MM-DD HH24:MI:SS');

ALTER TABLE orders DISABLE ROW MOVEMENT;
```

## 第四步：Flashback Drop（回收站恢复）

**适用场景**：误 DROP TABLE（非 PURGE）。

```sql
-- 查看回收站
SELECT object_name, original_name, type, droptime
FROM recyclebin
ORDER BY droptime DESC;

-- 恢复表
FLASHBACK TABLE orders TO BEFORE DROP;

-- 名称冲突时重命名恢复
FLASHBACK TABLE orders TO BEFORE DROP RENAME TO orders_recovered;
```

## 第五步：Flashback Database（数据库级回退）

**适用场景**：批量错误操作影响多张表，需整库回退。

```sql
-- 需已启用 Flashback Database
STARTUP MOUNT;
FLASHBACK DATABASE TO TIMESTAMP
    TO_TIMESTAMP('2026-03-20 07:00:00','YYYY-MM-DD HH24:MI:SS');
ALTER DATABASE OPEN RESETLOGS;
```

## 第六步：RMAN 时间点恢复（PITR）

**适用场景**：Undo 已过期，需从备份中恢复。

```sql
RUN {
    SET UNTIL TIME "TO_DATE('2026-03-20 07:00:00','YYYY-MM-DD HH24:MI:SS')";
    RESTORE DATABASE;
    RECOVER DATABASE;
}
ALTER DATABASE OPEN RESETLOGS;
```

## 第七步：LogMiner 挖掘 Redo 日志

**适用场景**：精确查找某时间段内执行的 DML，审计恢复。

```sql
-- 添加日志文件并启动 LogMiner
EXEC DBMS_LOGMNR.ADD_LOGFILE('/arch/1_100_xxx.arc');
EXEC DBMS_LOGMNR.START_LOGMNR(
    STARTTIME => TO_DATE('2026-03-20 07:00:00','YYYY-MM-DD HH24:MI:SS'),
    ENDTIME   => TO_DATE('2026-03-20 09:00:00','YYYY-MM-DD HH24:MI:SS'),
    OPTIONS   => DBMS_LOGMNR.DICT_FROM_ONLINE_CATALOG
);

-- 查询被删除的数据及对应的撤销 SQL
SELECT scn, timestamp, operation, sql_redo, sql_undo
FROM v$logmnr_contents
WHERE seg_name = 'ORDERS'
  AND operation = 'DELETE'
ORDER BY scn;

EXEC DBMS_LOGMNR.END_LOGMNR();
```

## 恢复方案决策树

| 场景 | 最优方案 |
|---|---|
| 误 DELETE，Undo 有效 | Flashback Query + INSERT |
| 误 DELETE 大量数据 | Flashback Table |
| 误 DROP TABLE | Flashback Drop（回收站） |
| 误操作影响多表 | Flashback Database |
| Undo 过期，有备份 | RMAN PITR |
| 需要精确 SQL 审计 | LogMiner |

## 预防措施

1. 开启 Flashback Database，设置足够的 `db_flashback_retention_target`（建议 1440 分钟）
2. 定期 RMAN 全备 + 增量备份
3. 生产环境大批量 DML 前先备份相关表（CREATE TABLE t_bak AS SELECT * FROM t）
4. 开启归档日志，确保 LogMiner 可用
"""
    },
    {
        "category": "配置与会话",
        "title": "Oracle 系统参数配置诊断优化流程",
        "content": r"""# Oracle 系统参数配置诊断优化流程

## 概述

Oracle 数据库有数百个初始化参数，核心参数配置不当会直接影响性能、稳定性和资源利用率。本文档涵盖 SGA/PGA 内存、连接限制、优化器、Redo Log、Undo、并行等关键参数的诊断与优化建议。

## 诊断技能调用顺序

1. `get_db_variables` — 获取当前参数值
2. `execute_diagnostic_query` — 分析参数使用效果（命中率、等待事件）
3. `get_os_metrics` — 获取主机内存与 CPU 资源（需配置 host）

## 第一步：内存参数诊断

### 调用 `get_db_variables` skill

```sql
-- 内存相关参数
SELECT name, value, description
FROM v$parameter
WHERE name IN (
    'memory_target', 'memory_max_target',
    'sga_target', 'sga_max_size',
    'pga_aggregate_target', 'pga_aggregate_limit',
    'db_cache_size', 'shared_pool_size',
    'large_pool_size', 'java_pool_size',
    'streams_pool_size', 'log_buffer'
)
ORDER BY name;

-- 当前 SGA 各组件实际使用
SELECT component, current_size/1024/1024 curr_mb,
       min_size/1024/1024 min_mb,
       max_size/1024/1024 max_mb
FROM v$sga_dynamic_components
ORDER BY current_size DESC;
```

**Buffer Cache 命中率检查**：

```sql
SELECT 1 - (phy.value / (cur.value + con.value)) hit_ratio
FROM v$sysstat phy, v$sysstat cur, v$sysstat con
WHERE phy.name = 'physical reads'
  AND cur.name = 'db block gets'
  AND con.name = 'consistent gets';
-- 正常 > 0.99，低于 0.95 需增大 db_cache_size
```

**Shared Pool 命中率**：

```sql
SELECT 1 - (SUM(CASE name WHEN 'library cache misses' THEN value ELSE 0 END) /
             NULLIF(SUM(CASE name WHEN 'library cache gets' THEN value ELSE 0 END), 0)) hit_ratio
FROM v$sysstat
WHERE name IN ('library cache gets', 'library cache misses');
-- 正常 > 0.99，低于 0.95 需增大 shared_pool_size
```

## 第二步：连接与会话参数

```sql
SELECT name, value FROM v$parameter
WHERE name IN (
    'processes', 'sessions', 'transactions',
    'open_cursors', 'session_cached_cursors'
);

-- 当前使用情况与上限比较
SELECT 'processes' resource_name,
       COUNT(*) current_utilization,
       (SELECT value FROM v$parameter WHERE name='processes') max_utilization
FROM v$process
UNION ALL
SELECT 'sessions',
       COUNT(*),
       (SELECT value FROM v$parameter WHERE name='sessions')
FROM v$session;
```

**建议**：processes 使用率 > 80% 时扩容；open_cursors 建议设置 1000~2000。

## 第三步：优化器参数

```sql
SELECT name, value FROM v$parameter
WHERE name IN (
    'optimizer_mode',
    'optimizer_features_enable',
    'optimizer_dynamic_sampling',
    'optimizer_adaptive_plans',
    'optimizer_adaptive_statistics',
    'cursor_sharing',
    'db_file_multiblock_read_count',
    'parallel_max_servers',
    'parallel_degree_policy'
)
ORDER BY name;
```

**关键建议**：
- `optimizer_mode = ALL_ROWS`（OLTP 推荐）
- `cursor_sharing = EXACT`（默认，避免执行计划不稳定）
- `optimizer_adaptive_plans = TRUE`（12c+ 推荐）
- `parallel_degree_policy = MANUAL`（OLTP 环境避免自动并行）

## 第四步：Redo 与 Undo 参数

```sql
SELECT name, value FROM v$parameter
WHERE name IN (
    'log_buffer',
    'log_checkpoint_interval',
    'log_checkpoint_timeout',
    'fast_start_mttr_target',
    'undo_management',
    'undo_tablespace',
    'undo_retention'
);
```

**建议**：
- `log_buffer`：建议 32MB~128MB（高写入负载）
- `fast_start_mttr_target`：设置期望恢复时间（秒），Oracle 自动调整 Checkpoint 频率
- `undo_retention`：建议 >= 900 秒，防止 ORA-01555

## 第五步：参数修改操作

```sql
-- 动态参数（立即生效）
ALTER SYSTEM SET pga_aggregate_target = 4G;
ALTER SYSTEM SET open_cursors = 1000;

-- 仅修改 SPFILE（重启后生效）
ALTER SYSTEM SET processes = 500 SCOPE=SPFILE;

-- 仅修改当前内存（不持久化）
ALTER SYSTEM SET log_buffer = 64M SCOPE=MEMORY;

-- 查看参数修改历史（11g+）
SELECT name, value, display_value, update_comment,
       to_char(change_date,'YYYY-MM-DD HH24:MI:SS') change_date
FROM v$spparameter_history
WHERE change_date > SYSDATE - 7
ORDER BY change_date DESC;
```

## 参数优化汇总表

| 参数 | 推荐值 | 说明 |
|---|---|---|
| sga_target | 物理内存 × 60% | AMM 自动管理 SGA 各组件 |
| pga_aggregate_target | 物理内存 × 20% | 自动 PGA 管理 |
| processes | 并发连接数 × 1.2 | 预留 20% 余量 |
| open_cursors | 1000~2000 | 防止 ORA-01000 |
| undo_retention | 900+ | 防止 ORA-01555 |
| log_buffer | 32M~128M | 高写入场景 |
"""
    },
    {
        "category": "配置与会话",
        "title": "Oracle 会话连接诊断优化流程",
        "content": r"""# Oracle 会话连接诊断优化流程

## 概述

Oracle 会话连接管理是日常运维的核心任务之一。常见问题包括：连接数耗尽（ORA-00018/ORA-12519）、大量 INACTIVE 空闲连接占用资源、连接泄漏、长时间阻塞会话、以及连接池配置不合理等。

## 诊断技能调用顺序

1. `get_process_list` — 查看当前所有会话状态
2. `execute_diagnostic_query` — 分析连接分布、长事务、锁等待
3. `get_db_variables` — 检查 processes/sessions 参数

## 第一步：会话总览

### 调用 `get_process_list` skill

```sql
-- 会话状态汇总
SELECT status, COUNT(*) cnt
FROM v$session
GROUP BY status
ORDER BY cnt DESC;

-- 按应用/机器统计会话
SELECT machine, program, username,
       COUNT(*) total_sessions,
       SUM(CASE status WHEN 'ACTIVE' THEN 1 ELSE 0 END) active,
       SUM(CASE status WHEN 'INACTIVE' THEN 1 ELSE 0 END) inactive
FROM v$session
WHERE type = 'USER'
GROUP BY machine, program, username
ORDER BY total_sessions DESC;
```

## 第二步：空闲会话与连接泄漏检测

### 调用 `execute_diagnostic_query` skill

```sql
-- 长时间 INACTIVE 会话（可能是连接泄漏）
SELECT sid, serial#, username, status,
       machine, program,
       ROUND((SYSDATE - last_call_et/86400)*86400) idle_sec,
       logon_time
FROM v$session
WHERE status = 'INACTIVE'
  AND username IS NOT NULL
  AND last_call_et > 1800  -- 空闲超过 30 分钟
ORDER BY last_call_et DESC;

-- 杀掉长时间空闲连接（需确认业务影响）
-- ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
```

## 第三步：长事务检测

```sql
-- 运行时间超过 10 分钟的活跃会话
SELECT s.sid, s.serial#, s.username, s.status,
       s.event, s.sql_id,
       ROUND(s.last_call_et/60, 1) running_min,
       s.machine, s.program
FROM v$session s
WHERE s.status = 'ACTIVE'
  AND s.username IS NOT NULL
  AND s.last_call_et > 600
ORDER BY s.last_call_et DESC;

-- 未提交事务
SELECT t.start_time, t.used_ublk * 8 / 1024 undo_mb,
       t.used_urec undo_records,
       s.username, s.sid, s.serial#, s.sql_id
FROM v$transaction t
JOIN v$session s ON t.ses_addr = s.saddr
ORDER BY t.used_ublk DESC;
```

## 第四步：阻塞会话处理

```sql
-- 阻塞会话树
SELECT LPAD(' ', (LEVEL-1)*2) || s.sid sid_tree,
       s.serial#, s.username, s.status,
       s.event, s.seconds_in_wait,
       s.blocking_session, s.sql_id
FROM v$session s
START WITH s.blocking_session IS NULL
       AND EXISTS (SELECT 1 FROM v$session s2
                   WHERE s2.blocking_session = s.sid)
CONNECT BY PRIOR s.sid = s.blocking_session
ORDER SIBLINGS BY s.seconds_in_wait DESC;

-- 终止阻塞会话
ALTER SYSTEM KILL SESSION '&sid,&serial#' IMMEDIATE;
```

## 第五步：PROFILE 与超时配置

```sql
-- 查看 Profile 资源限制
SELECT profile, resource_name, limit
FROM dba_profiles
WHERE resource_name IN (
    'CONNECT_TIME', 'IDLE_TIME',
    'SESSIONS_PER_USER', 'CPU_PER_SESSION'
)
ORDER BY profile, resource_name;

-- 设置空闲超时（分钟）
ALTER PROFILE default LIMIT IDLE_TIME 60;

-- sqlnet.ora 配置 Dead Connection Detection
-- SQLNET.EXPIRE_TIME = 10  (每 10 分钟检测一次死连接)
```

## 第六步：连接池最佳实践

```sql
-- 检查 DRCP（Database Resident Connection Pool）状态
SELECT connection_pool, status, minsize, maxsize,
       incrsize, timeout,
       num_open_servers, num_busy_servers, num_auth_servers
FROM v$cpool_stats;

-- 启动 DRCP
EXEC DBMS_CONNECTION_POOL.START_POOL(
    pool_name   => 'SYS_DEFAULT_CONNECTION_POOL',
    minsize     => 4,
    maxsize     => 40,
    incrsize    => 2,
    session_cached_cursors => 20,
    inactivity_timeout => 300
);
```

## 优化建议汇总

| 问题 | 处理方法 |
|---|---|
| 连接数耗尽 | 增大 processes，使用连接池（DRCP 或应用层） |
| 大量空闲连接 | 配置 IDLE_TIME Profile，应用层设置连接超时 |
| 连接泄漏 | 应用侧检查连接释放逻辑，配置 DCD |
| 长事务阻塞 | 终止阻塞会话，优化事务粒度 |
| 大量来自同一机器 | 检查该应用连接池配置，是否存在连接未归还 |
"""
    },
    {
        "category": "安全与权限",
        "title": "Oracle 安全诊断方案",
        "content": r"""# Oracle 安全诊断方案

## 概述

Oracle 数据库安全诊断涵盖认证方式、网络加密、审计配置、默认账户管理、权限最小化、数据库版本补丁等多个维度。定期安全审计是数据库合规运维的基本要求，可参考 CIS Oracle Benchmark 标准执行。

## 诊断技能调用顺序

1. `execute_diagnostic_query` — 检查用户、权限、审计配置
2. `get_db_status` — 检查数据库版本与补丁状态
3. `get_db_variables` — 检查安全相关参数

## 第一步：用户账户安全检查

### 调用 `execute_diagnostic_query` skill

```sql
-- 检查所有非系统账户状态
SELECT username, account_status, lock_date,
       expiry_date, created, profile,
       authentication_type
FROM dba_user
WHERE oracle_maintained = 'N'
ORDER BY account_status, username;

-- 默认密码风险用户（与常见弱密码对比）
SELECT u.username, u.account_status
FROM dba_user u
JOIN sys.user$ su ON u.username = su.name
WHERE su.password IN (
    SELECT password FROM sys.user$
    WHERE name IN ('SCOTT', 'HR', 'OE', 'SH', 'DBSNMP')
)
  AND u.account_status = 'OPEN';

-- 使用默认 Profile 的用户（默认 Profile 安全限制宽松）
SELECT username, profile, account_status
FROM dba_user
WHERE profile = 'DEFAULT'
  AND oracle_maintained = 'N'
  AND account_status = 'OPEN';
```

## 第二步：系统权限审查

```sql
-- 拥有 DBA 权限的用户
SELECT grantee, granted_role, admin_option, default_role
FROM dba_role_privs
WHERE granted_role = 'DBA'
ORDER BY grantee;

-- 拥有高危系统权限的用户
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE privilege IN (
    'ALTER SYSTEM', 'ALTER DATABASE', 'CREATE ANY TABLE',
    'DROP ANY TABLE', 'EXECUTE ANY PROCEDURE',
    'SELECT ANY DICTIONARY', 'BECOME USER',
    'CREATE USER', 'DROP USER', 'GRANT ANY PRIVILEGE'
)
  AND grantee NOT IN ('SYS', 'SYSTEM', 'DBA', 'IMP_FULL_DATABASE')
ORDER BY grantee, privilege;

-- PUBLIC 上不应有的权限
SELECT privilege, object_type, owner, table_name
FROM dba_tab_privs
WHERE grantee = 'PUBLIC'
  AND privilege IN ('EXECUTE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE')
  AND owner IN ('SYS', 'SYSTEM')
ORDER BY privilege, table_name;
```

## 第三步：审计配置检查

```sql
-- 检查统一审计策略（12c+）
SELECT policy_name, enabled_option, entity_name,
       success, failure
FROM audit_unified_enabled_policies
ORDER BY policy_name;

-- 传统审计（11g 及以下）
SELECT user_name, proxy_name, audit_option,
       success, failure
FROM dba_stmt_audit_opts
WHERE user_name IS NOT NULL
ORDER BY user_name;

-- 查看最近的审计记录（高危操作）
SELECT event_timestamp, db_username, os_username,
       action_name, object_schema, object_name,
       return_code, sql_text
FROM unified_audit_trail
WHERE event_timestamp > SYSDATE - 1
  AND action_name IN ('DROP TABLE', 'DROP USER', 'GRANT',
                      'ALTER SYSTEM', 'CREATE USER')
ORDER BY event_timestamp DESC;
```

## 第四步：网络传输安全

```sql
-- 检查 sqlnet.ora 加密配置（通过 v$parameter）
SELECT name, value FROM v$parameter
WHERE name IN (
    'sqlnet.encryption_server',
    'sqlnet.encryption_client',
    'sqlnet.crypto_checksum_server',
    'sqlnet.crypto_checksum_client'
);

-- 检查监听器是否只监听授权 IP
-- 在 listener.ora 中配置 VALID_NODE_CHECKING_REGISTRATION=ON
-- 在 sqlnet.ora 中配置 TCP.VALIDNODE_CHECKING=YES
```

## 第五步：版本与补丁检查

### 调用 `get_db_status` skill

```sql
-- 数据库版本信息
SELECT banner FROM v$version;

-- 已安装补丁（12c+）
SELECT patch_id, patch_uid, version,
       action, status, description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

## 安全加固建议

| 检查项 | 加固措施 |
|---|---|
| 默认账户开放 | 锁定不使用的账户：ALTER USER scott ACCOUNT LOCK |
| 弱密码 Profile | 创建强密码策略 Profile，设置复杂度验证函数 |
| DBA 权限过多 | 最小权限原则，按需授权，避免直接授予 DBA |
| PUBLIC 权限过宽 | REVOKE 高危权限：REVOKE EXECUTE ON UTL_FILE FROM PUBLIC |
| 无审计配置 | 启用统一审计，覆盖 DDL、权限变更、登录失败 |
| 传输未加密 | 配置 Oracle Native Network Encryption 或 SSL/TLS |
| 补丁落后 | 定期应用 CPU（Critical Patch Update） |
"""
    },
    {
        "category": "安全与权限",
        "title": "Oracle 用户权限诊断方案",
        "content": r"""# Oracle 用户权限诊断方案

## 概述

Oracle 权限体系分为系统权限（System Privileges）、对象权限（Object Privileges）和角色（Roles）三个层次。权限诊断的目标是识别权限过度授予、角色滥用、权限继承链不合理等问题，落实最小权限原则（Least Privilege Principle）。

## 诊断技能调用顺序

1. `execute_diagnostic_query` — 分析用户权限、角色继承链
2. `get_db_status` — 检查审计日志中的权限使用记录

## 第一步：用户权限全景查询

### 调用 `execute_diagnostic_query` skill

```sql
-- 某用户的所有系统权限（含通过角色继承的）
SELECT privilege, 'DIRECT' grant_type, admin_option
FROM dba_sys_privs
WHERE grantee = UPPER('&username')
UNION ALL
SELECT sp.privilege, 'VIA ROLE: ' || rp.granted_role, sp.admin_option
FROM dba_role_privs rp
JOIN dba_sys_privs sp ON rp.granted_role = sp.grantee
WHERE rp.grantee = UPPER('&username')
ORDER BY grant_type, privilege;

-- 某用户的所有对象权限
SELECT owner, table_name, privilege,
       grantable, hierarchy
FROM dba_tab_privs
WHERE grantee = UPPER('&username')
ORDER BY owner, table_name, privilege;
```

## 第二步：角色权限继承链分析

```sql
-- 查看角色层次结构（角色中的角色）
SELECT granted_role, grantee, admin_option, default_role
FROM dba_role_privs
WHERE grantee = UPPER('&role_or_user')
ORDER BY granted_role;

-- 递归查询某用户的完整角色树
SELECT LEVEL lvl,
       LPAD(' ', (LEVEL-1)*2) || granted_role role_tree,
       grantee
FROM dba_role_privs
START WITH grantee = UPPER('&username')
CONNECT BY PRIOR granted_role = grantee
ORDER SIBLINGS BY granted_role;

-- DBA 角色的权限清单（了解其范围）
SELECT privilege, admin_option
FROM dba_sys_privs
WHERE grantee = 'DBA'
ORDER BY privilege;
```

## 第三步：过度权限识别

```sql
-- 非 DBA 用户但拥有 ANY 权限
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE privilege LIKE '%ANY%'
  AND grantee NOT IN (
      SELECT grantee FROM dba_role_privs
      WHERE granted_role = 'DBA'
  )
  AND grantee NOT IN ('SYS', 'SYSTEM', 'XDB', 'APEX_040200')
ORDER BY grantee, privilege;

-- 可以创建/删除用户的非 DBA 用户
SELECT grantee, privilege
FROM dba_sys_privs
WHERE privilege IN ('CREATE USER', 'DROP USER', 'ALTER USER')
  AND grantee NOT IN ('DBA', 'SYS', 'SYSTEM')
ORDER BY grantee;

-- 对 SYS 对象有直接访问权限的普通用户
SELECT grantee, owner, table_name, privilege
FROM dba_tab_privs
WHERE owner = 'SYS'
  AND grantee NOT IN (
      'PUBLIC', 'DBA', 'SYS', 'SYSTEM', 'SELECT_CATALOG_ROLE'
  )
ORDER BY grantee, table_name
FETCH FIRST 50 ROWS ONLY;
```

## 第四步：权限使用审计

```sql
-- 查询近期权限变更审计记录
SELECT event_timestamp, db_username,
       action_name, system_privilege_used,
       object_schema, object_name, sql_text
FROM unified_audit_trail
WHERE action_name IN ('GRANT', 'REVOKE', 'CREATE USER',
                      'DROP USER', 'ALTER USER')
  AND event_timestamp > SYSDATE - 30
ORDER BY event_timestamp DESC;

-- 检查 WITH GRANT OPTION（可传递授权的危险权限）
SELECT grantee, owner, table_name, privilege, grantable
FROM dba_tab_privs
WHERE grantable = 'YES'
  AND grantee NOT IN ('SYS', 'SYSTEM', 'DBA')
ORDER BY grantee, table_name;
```

## 第五步：权限清理操作

```sql
-- 撤销系统权限
REVOKE CREATE ANY TABLE FROM username;
REVOKE DBA FROM username;

-- 撤销对象权限
REVOKE SELECT, INSERT ON schema.table_name FROM username;

-- 撤销角色
REVOKE dba_role FROM username;

-- 锁定不再使用的账户
ALTER USER old_app_user ACCOUNT LOCK;

-- 创建最小权限角色（示例：只读应用账户）
CREATE ROLE app_readonly;
GRANT CREATE SESSION TO app_readonly;
GRANT SELECT ON app_schema.orders TO app_readonly;
GRANT SELECT ON app_schema.customers TO app_readonly;
GRANT app_readonly TO app_user;
```

## 第六步：行级安全（VPD/RLS）

对于需要细粒度数据访问控制的场景，可使用 Virtual Private Database：

```sql
-- 创建 VPD 策略函数
CREATE OR REPLACE FUNCTION dept_filter(
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2 AS
BEGIN
    RETURN 'dept_id = SYS_CONTEXT(''USERENV'', ''CLIENT_IDENTIFIER'')';
END;
/

-- 绑定策略到表
EXEC DBMS_RLS.ADD_POLICY(
    object_schema   => 'HR',
    object_name     => 'EMPLOYEES',
    policy_name     => 'DEPT_POLICY',
    function_schema => 'HR',
    policy_function => 'DEPT_FILTER',
    statement_types => 'SELECT, INSERT, UPDATE, DELETE'
);
```

## 权限管理最佳实践

| 原则 | 具体措施 |
|---|---|
| 最小权限 | 只授予用户完成工作所必需的最小权限集 |
| 角色管理 | 通过角色聚合权限，避免直接授予对象权限 |
| 定期审查 | 每季度审查权限列表，回收离职人员权限 |
| 禁用默认账户 | 锁定所有 Oracle 内置测试账户 |
| 分离职责 | DBA 操作账户与应用账户严格分离 |
"""
    },
    {
        "category": "技术参考",
        "title": "Oracle Redo Log技术细节",
        "content": r"""# Oracle Redo Log技术细节

## 概述

Oracle Redo Log（重做日志）是数据库恢复机制的核心。每次数据修改（INSERT/UPDATE/DELETE/DDL）都会产生 Redo 记录，由 LGWR 后台进程写入联机 Redo Log 文件。Redo Log 保障了 Oracle 的 ACID 事务特性和崩溃恢复能力，同时也是 Data Guard 和 GoldenGate 数据复制的基础。

## Redo Log 架构

### 核心组件

| 组件 | 说明 |
|---|---|
| Log Buffer | SGA 中的环形缓冲区，事务先写入此处 |
| LGWR 进程 | 将 Log Buffer 写入联机 Redo Log 文件 |
| 联机 Redo Log | 循环使用的日志文件组（至少 2 组） |
| 归档日志 | 联机日志切换时归档保存，用于介质恢复 |
| ARCH 进程 | 负责归档日志文件 |

### LGWR 触发条件

- 事务 COMMIT
- Log Buffer 使用超过 1/3
- Log Buffer 中脏数据 > 1MB
- DBWR 写脏块前（确保 WAL 原则：Write-Ahead Logging）
- 每 3 秒定时写入

## Redo Log 状态查询

### 调用 `execute_diagnostic_query` skill

```sql
-- 联机 Redo Log 组状态
SELECT l.group#, l.thread#, l.sequence#,
       l.bytes/1024/1024 size_mb, l.members,
       l.status, l.archived, l.first_change#,
       l.first_time
FROM v$log l
ORDER BY l.thread#, l.group#;

-- Redo Log 文件路径
SELECT group#, member, status, type
FROM v$logfile
ORDER BY group#, member;

-- Redo Log 切换历史（近 24 小时）
SELECT TO_CHAR(first_time,'YYYY-MM-DD HH24:MI:SS') switch_time,
       sequence#, thread#,
       blocks * block_size / 1024 / 1024 size_mb
FROM v$archived_log
WHERE first_time > SYSDATE - 1
  AND standby_dest = 'NO'
ORDER BY first_time DESC;

-- 按小时统计切换频率
SELECT TO_CHAR(first_time,'YYYY-MM-DD HH24') log_hour,
       COUNT(*) switches_per_hour
FROM v$archived_log
WHERE first_time > SYSDATE - 7
  AND standby_dest = 'NO'
GROUP BY TO_CHAR(first_time,'YYYY-MM-DD HH24')
ORDER BY 1 DESC
FETCH FIRST 48 ROWS ONLY;
```

## Redo 生成统计

```sql
-- Redo 生成速率
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'redo size',             -- 总 Redo 字节数
    'redo writes',           -- LGWR 写次数
    'redo write time',       -- LGWR 写总时间（百分之一秒）
    'redo blocks written',   -- 写入的 Redo 块数
    'redo log space requests', -- 等待 Redo 空间的次数
    'redo log space wait time' -- 等待 Redo 空间的总时间
);

-- 计算平均 LGWR 写延迟
-- avg_write_ms = (redo write time / redo writes) * 10
-- 正常应 < 5ms，> 20ms 说明 IO 有问题
```

## log file sync 等待分析

`log file sync` 是 COMMIT 时等待 LGWR 将 Log Buffer 写入磁盘的等待事件，是最常见的写入性能瓶颈。

```sql
-- log file sync 统计
SELECT event, total_waits, total_timeouts,
       time_waited, max_wait,
       ROUND(time_waited/GREATEST(total_waits,1),2) avg_ms
FROM v$system_event
WHERE event = 'log file sync';

-- 关联 log file parallel write（LGWR IO 等待）
SELECT event, total_waits, time_waited,
       ROUND(time_waited/GREATEST(total_waits,1),2) avg_ms
FROM v$system_event
WHERE event IN ('log file sync', 'log file parallel write')
ORDER BY event;
```

**若 log file sync >> log file parallel write**：说明 LGWR 写 IO 正常，问题在于提交频率过高（过多小事务），解决方案是合并提交。

**若 log file sync ≈ log file parallel write**：说明 LGWR 写 IO 本身慢，需优化存储（将 Redo 日志移至 SSD 或 NVMe）。

## Redo Log 配置优化

```sql
-- 添加 Redo Log 组（建议至少 4 组）
ALTER DATABASE ADD LOGFILE GROUP 4
    ('/u01/redo04a.log', '/u02/redo04b.log') SIZE 1G;

-- 增大现有日志文件（需先删除再添加，非当前状态才能删除）
-- 1. 添加新的大文件组
ALTER DATABASE ADD LOGFILE GROUP 5
    ('/u01/redo05.log') SIZE 1G;
-- 2. 触发日志切换到新组
ALTER SYSTEM SWITCH LOGFILE;
-- 3. 等待旧组状态变为 INACTIVE，然后删除
ALTER DATABASE DROP LOGFILE GROUP 1;
-- 4. 重新添加更大的文件
ALTER DATABASE ADD LOGFILE GROUP 1 ('/u01/redo01.log') SIZE 1G;

-- 手动触发日志切换（测试或维护用）
ALTER SYSTEM SWITCH LOGFILE;

-- 手动触发 Checkpoint
ALTER SYSTEM CHECKPOINT;
```

## 归档日志管理

```sql
-- 开启归档模式（需在 MOUNT 状态执行）
-- SHUTDOWN IMMEDIATE;
-- STARTUP MOUNT;
-- ALTER DATABASE ARCHIVELOG;
-- ALTER DATABASE OPEN;

-- 配置归档目标
ALTER SYSTEM SET log_archive_dest_1 = 'LOCATION=/arch/primary';
ALTER SYSTEM SET log_archive_dest_2 = 'SERVICE=standby ASYNC';

-- RMAN 删除过期归档
RMAN> DELETE ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-3';
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
```

## 多路复用 Redo Log 最佳实践

1. 至少 3 组 Redo Log，每组 2 个成员（分布在不同磁盘/存储阵列）
2. 日志文件大小：OLTP 建议 512MB~2GB，高吞吐量场景 2GB~4GB
3. Redo Log 文件应放在 I/O 延迟最低的存储上（SSD 优先）
4. 切换频率：正常应每 15~30 分钟切换一次
5. FRA（快速恢复区）空间应足够保存 2~3 天的归档日志
"""
    },
    {
        "category": "技术参考",
        "title": "Oracle 错误码查询（ORA-错误）",
        "content": r"""# Oracle 错误码查询（ORA-错误）

## 概述

Oracle 错误码（ORA-XXXXX）是数据库运维中最常见的问题入口。本文档汇总运维中最高频的 ORA 错误码，提供每个错误的含义、常见原因、诊断 SQL 和解决方案，可作为快速参考手册使用。

## 诊断技能调用

- `get_db_status` — 查看告警日志中的错误记录
- `execute_diagnostic_query` — 针对特定错误执行诊断 SQL
- `get_db_variables` — 检查相关参数配置

## 连接与会话类错误

### ORA-00018：超出最大会话数

**原因**：活跃会话数达到 `sessions` 参数上限。

```sql
SELECT COUNT(*) current_sessions,
       (SELECT value FROM v$parameter WHERE name='sessions') max_sessions
FROM v$session;

-- 解决：增大 sessions（需同步增大 processes）
ALTER SYSTEM SET processes = 500 SCOPE=SPFILE;
-- 重启数据库生效
```

### ORA-01017：用户名/密码无效，登录被拒绝

```sql
-- 检查用户状态
SELECT username, account_status, lock_date, profile
FROM dba_user WHERE username = UPPER('&user');

-- 解锁账户
ALTER USER username ACCOUNT UNLOCK;
ALTER USER username IDENTIFIED BY new_password;
```

### ORA-28000：账户已锁定

```sql
-- 查看 Profile 锁定策略
SELECT profile, resource_name, limit FROM dba_profiles
WHERE resource_name = 'FAILED_LOGIN_ATTEMPTS';

-- 解锁
ALTER USER username ACCOUNT UNLOCK;
```

### ORA-12541：TNS 无监听程序

```bash
# 检查监听状态
lsnrctl status
lsnrctl start

# 检查端口是否在监听
netstat -tlnp | grep 1521
```

## 空间类错误

### ORA-01653 / ORA-01654：无法将段扩展至表空间

```sql
-- 找出空间不足的表空间
SELECT tablespace_name, SUM(bytes)/1024/1024 free_mb
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY free_mb;

-- 扩展表空间
ALTER TABLESPACE user ADD DATAFILE '/u01/user02.dbf' SIZE 5G AUTOEXTEND ON;
-- 或扩展现有数据文件
ALTER DATABASE DATAFILE '/u01/user01.dbf' RESIZE 20G;
```

### ORA-01555：快照太旧

**原因**：长查询需要的 Undo 数据已被覆盖。

```sql
SELECT name, value FROM v$parameter
WHERE name IN ('undo_retention', 'undo_tablespace');

SELECT MAX(tuned_undoretention) tuned_sec,
       MAX(maxquerylen) max_query_sec
FROM v$undostat;

-- 增大 undo_retention
ALTER SYSTEM SET undo_retention = 3600;
-- 增大 Undo 表空间
ALTER TABLESPACE undotbs1 ADD DATAFILE '/u01/undo02.dbf' SIZE 10G;
```

### ORA-30036：无法在 Undo 表空间中扩展段

```sql
-- 检查 Undo 表空间使用
SELECT status, SUM(blocks)*8/1024 mb
FROM dba_undo_extents GROUP BY status;

-- 扩展 Undo 表空间
ALTER TABLESPACE undotbs1 ADD DATAFILE '/u01/undo03.dbf' SIZE 5G;
```

## 内存类错误

### ORA-04031：共享池无法分配内存

```sql
-- 共享池使用情况
SELECT pool, name, bytes/1024/1024 mb
FROM v$sgastat
WHERE pool = 'shared pool'
  AND bytes > 5*1024*1024
ORDER BY bytes DESC;

-- 刷新共享池（谨慎，会清除缓存的 SQL）
ALTER SYSTEM FLUSH SHARED_POOL;

-- 增大 shared_pool_size
ALTER SYSTEM SET shared_pool_size = 2G;
```

### ORA-04030：进程无法分配 PGA 内存

```sql
SELECT name, value/1024/1024 mb
FROM v$pgastat
WHERE name IN ('total PGA inuse', 'aggregate PGA target parameter',
               'cache hit percentage');

-- 增大 PGA
ALTER SYSTEM SET pga_aggregate_target = 8G;
```

## 锁与并发错误

### ORA-00060：等待死锁检测（Deadlock Detected）

```sql
-- 查看告警日志中的死锁记录
SELECT originating_timestamp, message_text
FROM v$diag_alert_ext
WHERE message_text LIKE '%ORA-00060%'
  AND originating_timestamp > SYSDATE - 1
ORDER BY originating_timestamp DESC;

-- 查看被锁对象
SELECT lo.oracle_username, do.object_name,
       lo.locked_mode
FROM v$locked_object lo
JOIN dba_objects do ON lo.object_id = do.object_id;
```

## 数据文件与恢复类错误

### ORA-01157：无法识别/锁定数据文件

```sql
SELECT file#, name, status FROM v$datafile;
SELECT file#, name, status FROM v$datafile_header;

-- 非系统文件离线
ALTER DATABASE DATAFILE &file# OFFLINE DROP;
ALTER DATABASE OPEN;
-- 之后 RMAN 恢复该数据文件
```

### ORA-00600：内部错误（Internal Error）

**处理步骤**：
1. 记录完整错误信息（ORA-00600 后的 [argument] 数组）
2. 在 My Oracle Support（MOS）搜索对应的 Bug ID
3. 收集 trace 文件：`SELECT value FROM v$diag_info WHERE name='Default Trace File'`
4. 开 SR 给 Oracle Support

### ORA-07445：OS 内核异常

类似 ORA-00600，需查 trace 文件和 MOS，通常需要打 Oracle Patch。

## 快速错误诊断流程

```sql
-- 查看最近 1 小时的所有 ORA 错误
SELECT originating_timestamp, message_text
FROM v$diag_alert_ext
WHERE originating_timestamp > SYSDATE - 1/24
  AND message_text LIKE 'ORA-%'
ORDER BY originating_timestamp DESC;

-- 统计错误类型分布
SELECT REGEXP_SUBSTR(message_text, 'ORA-[0-9]+') ora_code,
       COUNT(*) cnt
FROM v$diag_alert_ext
WHERE originating_timestamp > SYSDATE - 1
  AND message_text LIKE 'ORA-%'
GROUP BY REGEXP_SUBSTR(message_text, 'ORA-[0-9]+')
ORDER BY cnt DESC;
```

## 常用 ORA 错误速查表

| ORA 错误码 | 含义 | 主要处理 |
|---|---|---|
| ORA-00018 | 超出最大会话数 | 增大 processes/sessions |
| ORA-00060 | 死锁 | 优化事务顺序，添加外键索引 |
| ORA-00600 | 内部错误 | 查 MOS，开 SR |
| ORA-01017 | 密码错误 | 重置密码，解锁账户 |
| ORA-01555 | 快照太旧 | 增大 undo_retention |
| ORA-01653 | 无法扩展段 | 扩展表空间 |
| ORA-04031 | 共享池不足 | 增大 shared_pool_size |
| ORA-04030 | PGA 不足 | 增大 pga_aggregate_target |
| ORA-12541 | 无监听 | 启动监听 lsnrctl start |
| ORA-28000 | 账户锁定 | ALTER USER ... ACCOUNT UNLOCK |
"""
    },
]
