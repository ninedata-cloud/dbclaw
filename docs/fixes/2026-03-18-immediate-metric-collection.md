# 主机操作后立即采集指标功能

## 问题描述

在添加、修改或测试主机后，用户需要等待最多 60 秒（下一个采集周期）才能在界面上看到主机的监控数据，体验不佳。

## 解决方案

在以下操作完成后立即触发一次指标采集：

1. **创建主机** (`POST /api/hosts`)
2. **更新主机** (`PUT /api/hosts/{host_id}`)
3. **测试主机连接** (`POST /api/hosts/{host_id}/test`)

## 实现细节

### 修改文件

`backend/routers/hosts.py`

### 关键代码

在每个操作的成功路径中添加：

```python
# Immediately collect metrics
try:
    from backend.services.host_collector import _collect_host_metrics
    await _collect_host_metrics(db, host)
    await db.commit()
    logger.info(f"Collected metrics after operation for host {host.name}")
except Exception as e:
    logger.warning(f"Failed to collect metrics for host {host.name}: {e}")
```

### 错误处理

- 指标采集失败不会影响主操作（创建/更新/测试）的成功
- 采集失败只记录警告日志，不抛出异常
- 后台定时采集器仍会在下一个周期重试

## 用户体验改进

- **创建主机**：保存后立即显示 CPU、内存、磁盘使用率
- **更新主机**：修改连接信息后立即验证并显示最新数据
- **测试连接**：测试成功后立即显示监控指标

## 测试验证

运行测试脚本：

```bash
python test_immediate_collection.py
```

预期结果：
- 操作后立即采集到新的指标数据
- 时间戳更新为当前时间
- 界面无需等待即可显示数据

## 相关修复

同时修复了中文系统环境下内存指标采集失败的问题（详见 `backend/services/host_collector.py`，使用 `LC_ALL=C` 强制英文输出）。

## 日期

2026-03-18
