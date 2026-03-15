# SQL Server OS 指标显示问题修复

## 问题描述

SQL Server 数据源在性能监控界面无法显示 OS 指标（CPU 使用率、内存使用率、磁盘使用率、负载平均）。

## 根本原因

SQL Server 数据源未配置 SSH 主机（`host_id` 为空），导致后端无法通过 SSH 采集 OS 指标。

## 解决方案

通过 SQL Server 的动态管理视图（DMV）直接查询 OS 指标，无需 SSH 连接。

## 代码修改

### 1. `backend/services/sqlserver_service.py`

在 `get_status()` 方法中添加 OS 指标采集：

```python
# CPU 使用率（通过 sys.dm_os_ring_buffers）
SELECT TOP 1 
100 - record.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS cpu_usage
FROM (
  SELECT CAST(record AS XML) AS record
  FROM sys.dm_os_ring_buffers
  WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
  AND record LIKE '%<SystemHealth>%'
) AS x
ORDER BY record.value('(./Record/@id)[1]', 'int') DESC

# 内存使用率（通过 sys.dm_os_sys_memory）
SELECT 
(total_physical_memory_kb - available_physical_memory_kb) * 100.0 / total_physical_memory_kb AS memory_usage
FROM sys.dm_os_sys_memory

# 磁盘使用率（数据库文件）
SELECT 
SUM(CAST(FILEPROPERTY(name, 'SpaceUsed') AS bigint) * 8) * 100.0 / 
SUM(CAST(size AS bigint) * 8) AS disk_usage
FROM sys.database_files

# 磁盘 I/O（通过 sys.dm_io_virtual_file_stats）
SELECT 
SUM(num_of_reads) AS total_reads,
SUM(num_of_writes) AS total_writes
FROM sys.dm_io_virtual_file_stats(NULL, NULL)

# 网络 I/O（通过 sys.dm_exec_connections）
SELECT 
SUM(num_reads) AS total_reads,
SUM(num_writes) AS total_writes
FROM sys.dm_exec_connections
```

### 2. `backend/services/metric_normalizer.py`

更新 `_normalize_sqlserver()` 方法，添加磁盘和网络 I/O 速率计算：

```python
# 计算磁盘 I/O 速率（从累积值计算）
if 'disk_reads_total' in metrics:
    reads_per_sec = cls._calculate_rate(
        datasource_id, 'disk_reads_total', metrics['disk_reads_total']
    )
    if reads_per_sec is not None:
        normalized['disk_reads_per_sec'] = reads_per_sec

if 'disk_writes_total' in metrics:
    writes_per_sec = cls._calculate_rate(
        datasource_id, 'disk_writes_total', metrics['disk_writes_total']
    )
    if writes_per_sec is not None:
        normalized['disk_writes_per_sec'] = writes_per_sec

# 计算网络 I/O 速率
if 'network_reads_total' in metrics:
    net_rx = cls._calculate_rate(
        datasource_id, 'network_reads_total', metrics['network_reads_total']
    )
    if net_rx is not None:
        normalized['network_rx_bytes'] = net_rx

if 'network_writes_total' in metrics:
    net_tx = cls._calculate_rate(
        datasource_id, 'network_writes_total', metrics['network_writes_total']
    )
    if net_tx is not None:
        normalized['network_tx_bytes'] = net_tx
```

## 验证结果

### 后端数据采集 ✅

最新采集的指标数据：

```json
{
    "cpu_usage": 0.0,
    "memory_usage": 10.82,
    "disk_usage": 28.0,
    "disk_reads_per_sec": 0.03,
    "disk_writes_per_sec": 28.93,
    "network_rx_bytes": 375932780291,
    "network_tx_bytes": 356704657090,
    "load_avg_1min": 0.08
}
```

### 历史数据趋势

```
时间                  | CPU  | 内存  | 磁盘  | 负载
---------------------|------|-------|-------|------
2026-03-15 05:38:31  | 0.0  | 10.82 | 28.0  | 0.08
2026-03-15 05:37:31  | 1.6  | 10.79 | 28.0  | 0.0
2026-03-15 05:36:13  | 1.6  | 10.79 | 28.0  | 0.02
2026-03-15 05:35:13  | 1.6  | 10.78 | 28.0  | 0.05
```

## 前端显示

前端代码 (`frontend/js/pages/monitor.js`) 已经支持显示这些指标，无需修改。

## 使用说明

### 如果前端仍然看不到 OS 指标

1. **强制刷新浏览器**：
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`

2. **清除浏览器缓存**：
   - Chrome: 设置 → 隐私和安全 → 清除浏览数据
   - Firefox: 选项 → 隐私与安全 → Cookie 和网站数据 → 清除数据

3. **检查浏览器控制台**：
   - 按 `F12` 打开开发者工具
   - 查看 Console 标签是否有 JavaScript 错误
   - 查看 Network 标签中的 WebSocket 连接
   - 在 WebSocket 消息中应该能看到包含 `cpu_usage`, `memory_usage` 等字段的数据

4. **验证 WebSocket 连接**：
   - 打开浏览器开发者工具（F12）
   - 切换到 Network 标签
   - 筛选 WS (WebSocket) 连接
   - 点击 WebSocket 连接，查看 Messages 标签
   - 应该能看到类似以下的消息：
     ```json
     {
       "type": "db_status",
       "datasource_id": 4,
       "data": {
         "cpu_usage": 0.0,
         "memory_usage": 10.82,
         "disk_usage": 28.0,
         ...
       }
     }
     ```

## 技术细节

### SQL Server DMV 说明

- **sys.dm_os_ring_buffers**: 环形缓冲区，包含系统健康信息（CPU 空闲率）
- **sys.dm_os_sys_memory**: 系统内存信息（总内存、可用内存）
- **sys.database_files**: 数据库文件信息（大小、已用空间）
- **sys.dm_io_virtual_file_stats**: 虚拟文件 I/O 统计（读写次数）
- **sys.dm_exec_connections**: 连接信息（网络读写次数）

### 指标计算方式

- **CPU 使用率**: `100 - SystemIdle`
- **内存使用率**: `(总内存 - 可用内存) / 总内存 * 100`
- **磁盘使用率**: `已用空间 / 总空间 * 100`
- **磁盘 I/O 速率**: 通过累积值计算增量速率（次/秒）
- **网络 I/O 速率**: 通过累积值计算增量速率（字节/秒）

## 注意事项

1. **权限要求**: SQL Server 用户需要有查询 DMV 的权限（VIEW SERVER STATE）
2. **性能影响**: DMV 查询对性能影响很小，可以安全地在生产环境使用
3. **数据准确性**: CPU 使用率基于环形缓冲区，可能有轻微延迟
4. **负载平均**: 如果配置了 SSH 主机，会从 SSH 主机采集；否则显示为 0

## 后续优化建议

1. 添加更多 SQL Server 特定的性能指标（等待统计、锁信息等）
2. 支持多实例监控（通过 SQL Server 实例名）
3. 添加性能计数器采集（通过 sys.dm_os_performance_counters）
4. 支持 Always On 可用性组监控

## 相关文件

- `backend/services/sqlserver_service.py` - SQL Server 连接器
- `backend/services/metric_normalizer.py` - 指标标准化服务
- `backend/services/metric_collector.py` - 指标采集服务
- `frontend/js/pages/monitor.js` - 前端监控页面

## 测试验证

```bash
# 查看最新采集的指标
sqlite3 data/smartdba.db "SELECT data FROM metric_snapshots WHERE datasource_id = 4 ORDER BY collected_at DESC LIMIT 1;" | python -m json.tool

# 查看历史趋势
sqlite3 data/smartdba.db "SELECT collected_at, json_extract(data, '$.cpu_usage'), json_extract(data, '$.memory_usage'), json_extract(data, '$.disk_usage') FROM metric_snapshots WHERE datasource_id = 4 ORDER BY collected_at DESC LIMIT 10;"
```

## 修复完成时间

2026-03-15 13:38
