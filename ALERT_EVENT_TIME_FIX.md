# 告警事件时间相关问题修复

## 问题 1：告警通知时间显示错误（时区问题）

### 问题描述

告警事件的告警时间和恢复时间显示错误，时间差了8小时。
- 实际应该显示：14:31:19（本地时间 UTC+8）
- 错误显示为：06:31:19（UTC时间）

### 根本原因

在 `backend/services/notification_dispatcher.py` 中，构建告警通知 payload 时使用了 `strftime()` 直接格式化 UTC 时间，没有转换为本地时区。

```python
# 错误的代码
timestamp = alert.created_at.strftime('%Y-%m-%d %H:%M:%S')
```

### 修复方案

1. 在 `backend/utils/datetime_helper.py` 中添加了两个新函数：
   - `to_local_time()`: 将 UTC datetime 转换为本地时间
   - `format_local_datetime()`: 将 UTC datetime 格式化为本地时间字符串

2. 在 `backend/services/notification_dispatcher.py` 中：
   - 导入 `format_local_datetime` 函数
   - 将所有 `strftime()` 调用替换为 `format_local_datetime()`
   - 影响的函数：
     - `_build_active_alert_payload()` (第246行)
     - `_build_recovery_alert_payload()` (第296-297行)

### 测试验证

创建了测试文件 `tests/test_notification_timezone_fix.py`，验证：
- UTC 时间 `2026-04-24 06:31:19` 正确转换为本地时间 `2026-04-24 14:31:19`

### 影响范围

此修复影响所有告警通知的时间显示：
- 飞书通知消息中的告警时间
- 恢复通知消息中的告警时间和恢复时间
- 所有告警 payload 中的 `timestamp`、`created_at`、`resolved_at` 字段

---

## 问题 2：告警事件最后时间未更新

### 问题描述

告警事件的 `event_ended_at`（最后时间）字段在持续告警时没有更新。

## 根本原因

发现了三个关键问题：

1. **缺少事务提交**：`collect_metrics_for_connection` 在调用 `_route_alert_engine` 和 `_handle_connection_failure` 后没有提交事务
2. **方法内部提交冲突**：`update_active_event_time` 方法内部调用了 `await db.commit()`，导致事务边界混乱
3. **异常处理缺失**：部分调用 `update_active_event_time` 的地方没有异常处理，commit 失败会中断流程

## 修复内容

### 1. 移除 `update_active_event_time` 内部的 commit

**文件**：`backend/services/alert_event_service.py`

**修改**：移除第 461 行的 `await db.commit()`，改为只 `flush()`，由调用方决定何时提交。

**原因**：方法不应该自己提交事务，应该遵循"调用方控制事务边界"的原则。

### 2. 在 `collect_metrics_for_connection` 末尾添加 commit

**文件**：`backend/services/metric_collector.py`

**位置**：第 198 行

**修改**：在 `_route_alert_engine` 和 `_handle_connection_failure` 执行后，添加 `await db.commit()`

**原因**：确保所有告警、巡检、事件时间更新都被持久化。

### 3. 为所有 `update_active_event_time` 调用添加异常处理

**文件**：`backend/services/metric_collector.py`

**位置**：
- 第 506-514 行（threshold_violation）
- 第 587-594 行（baseline_deviation）
- 第 831-844 行（connection_status）
- 第 915-925 行（network_probe）

**修改**：用 try-except 包裹调用，捕获异常并记录警告日志。

**原因**：防止事件时间更新失败导致整个采集流程中断。

## 测试验证

运行测试：
```bash
python -m tests.test_alert_event_time_update
```

测试覆盖：
1. 更新活跃事件的最后时间
2. 已解决事件不会被更新

## 影响范围

- 阈值告警去重时的事件时间更新
- 基线告警去重时的事件时间更新
- 连接失败告警去重时的事件时间更新
- 网络探针告警去重时的事件时间更新
- AI 告警去重时的事件时间更新

## 重要发现

1. `async with async_session() as db:` **不会自动 commit**，必须显式调用 `await db.commit()`
2. 服务方法应该只 `flush()`，不应该 `commit()`，除非它自己创建了 session
3. 异常处理很重要，避免一个子功能失败导致整个流程中断

## 相关文件

- `backend/services/alert_event_service.py`
- `backend/services/metric_collector.py`
- `backend/services/alert_ai_service.py`
- `tests/test_alert_event_time_update.py`

## 修复日期

2026-04-24
