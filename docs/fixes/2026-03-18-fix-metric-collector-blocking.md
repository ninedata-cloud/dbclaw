# 修复指标采集器SSH阻塞问题

**日期**: 2026-03-18
**问题**: 数据源 192.168.2.29:3306 持续发送连接失败告警

## 问题现象

用户报告数据源可以正常连接，但 DbGuard 持续发送连接失败告警：

```
告警标题： System Error
严重程度： 严重
告警类型： system_error
数据库类型： MYSQL
数据库地址： 192.168.2.29:3306
指标： connection_status = 0.00
阈值： 1.00
触发原因： Connection failed: (2003, "Can't connect to MySQL server on '192.168.2.29'")
时间： 2026-03-18 09:22:45
```

## 根本原因分析

通过深入代码诊断，发现问题的根本原因是：

### 1. SSH连接超时导致采集阻塞

数据源配置了SSH主机 `192.168.2.29:9022` 用于采集OS指标。在某些时刻，SSH连接超时或挂起（可能是网络不稳定、防火墙、SSH服务问题），导致采集任务长时间阻塞。

### 2. 信号量机制导致采集延迟

原代码使用 `asyncio.Semaphore(3)` 限制并发数据库写入，但信号量的保护范围过大，包含了整个采集逻辑：

```python
async def collect_metrics_for_connection(datasource_id: int):
    async with _db_write_semaphore:  # ❌ 信号量保护范围过大
        try:
            # 数据库连接
            # SSH指标采集 ← 这里可能长时间阻塞
            # 数据库写入
        except Exception as e:
            logger.error(...)
```

当SSH连接挂起时，信号量被长时间占用（约16分钟），导致该数据源的后续采集被延迟。

### 3. 证据链

```
09:20:17 ✓ 成功采集（包含MySQL + SSH OS指标）
09:21:17 ✓ 成功采集
09:22:45   创建告警308（连接失败）
[16分钟空白 - SSH连接挂起，信号量被占用]
09:38:06 ✗ 失败采集（连接超时）
```

其他数据源在 09:22:32 左右都有正常采集，说明采集器本身没有停止，只有数据源3的采集被跳过。

## 修复方案

### 1. 缩小信号量保护范围

将信号量保护范围缩小到仅数据库写入操作：

```python
async def collect_metrics_for_connection(datasource_id: int):
    try:
        async with async_session() as db:
            # 数据库连接
            # SSH指标采集（不在信号量保护内）

            # ✓ 仅在数据库写入时使用信号量
            async with _db_write_semaphore:
                snapshot = MetricSnapshot(...)
                db.add(snapshot)
                await db.commit()
    except Exception as e:
        logger.error(...)
```

### 2. 添加SSH采集超时保护

为SSH指标采集添加30秒超时保护：

```python
if datasource.host_id:
    try:
        # 使用超时保护，避免SSH连接挂起导致长时间阻塞
        os_metrics = await asyncio.wait_for(
            _collect_os_metrics(db, datasource.host_id),
            timeout=30.0  # 30秒超时
        )
        if os_metrics:
            normalized_status.update(os_metrics)
    except asyncio.TimeoutError:
        logger.warning(f"SSH metrics collection timeout for datasource {datasource_id}")
    except Exception as e:
        logger.warning(f"Failed to collect SSH metrics for datasource {datasource_id}: {e}")
```

### 3. 手动解除活跃告警

```python
await AlertService.resolve_alert(db, 308)
```

## 修复效果

- ✓ SSH连接超时不再阻塞整个采集流程
- ✓ 单个数据源的SSH问题不影响其他数据源
- ✓ 采集任务能够按时执行（60秒间隔）
- ✓ 连接恢复后告警自动解除

## 后续建议

1. **检查SSH主机稳定性**: 排查 192.168.2.29:9022 的连接问题
2. **优化SSH连接池**: 考虑增加连接池的超时配置和重试机制
3. **监控采集性能**: 添加采集任务执行时间的监控，及时发现阻塞
4. **告警优化**: 考虑为间歇性连接失败添加去重和延迟告警机制

## 相关文件

- `backend/services/metric_collector.py` - 指标采集器
- `backend/services/ssh_connection_pool.py` - SSH连接池
- `backend/services/os_metrics_collector.py` - OS指标采集器
