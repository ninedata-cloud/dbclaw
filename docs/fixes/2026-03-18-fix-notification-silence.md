# 修复：静默期间仍发送告警通知

**日期**: 2026-03-18
**问题**: 设置数据源静默后，仍然收到飞书告警通知

## 问题分析

### 根本原因

通知分发器（`notification_dispatcher.py`）在发送告警通知时，**没有检查数据源的静默状态**。

### 问题场景

1. 数据源在 13:18 产生连接失败告警（告警ID: 324）
2. 用户在 14:35 设置数据源静默1小时
3. 通知分发器每30秒运行一次，处理待发送的告警
4. 分发器发现告警324是活跃状态，直接发送通知
5. **没有检查数据源是否在静默期内**

### 代码问题

原代码在 `_process_pending_alerts()` 中：

```python
for alert in alerts:
    for subscription in subscriptions:
        # 直接处理告警，没有检查静默状态
        if not await NotificationService.check_subscription_match(alert, subscription):
            continue
        # ... 发送通知
```

## 修复方案

### 1. 添加静默检查函数

在 `notification_dispatcher.py` 中添加：

```python
async def _is_datasource_silenced(db, datasource_id: int) -> bool:
    """Check if a datasource is currently in silence period"""
    from sqlalchemy import select
    from backend.models.datasource import Datasource
    from backend.utils.datetime_helper import now

    result = await db.execute(
        select(Datasource).where(Datasource.id == datasource_id)
    )
    datasource = result.scalar_one_or_none()

    if not datasource or not datasource.silence_until:
        return False

    current_time = now()
    if current_time < datasource.silence_until:
        return True

    # Silence period expired, clear it
    datasource.silence_until = None
    datasource.silence_reason = None
    await db.commit()
    return False
```

### 2. 在发送通知前检查静默状态

修改 `_process_pending_alerts()`：

```python
for alert in alerts:
    # ✓ 新增：检查数据源是否在静默期内
    if await _is_datasource_silenced(db, alert.datasource_id):
        logger.debug(f"Skipping alert {alert.id}: datasource {alert.datasource_id} is silenced")
        continue

    for subscription in subscriptions:
        # ... 发送通知
```

### 3. 修复恢复通知

同样在 `_process_recovery_notifications()` 中添加静默检查：

```python
for alert in resolved_alerts:
    # ✓ 新增：检查数据源是否在静默期内
    if await _is_datasource_silenced(db, alert.datasource_id):
        logger.debug(f"Skipping recovery notification for alert {alert.id}: datasource {alert.datasource_id} is silenced")
        continue

    for subscription in subscriptions:
        # ... 发送恢复通知
```

## 修复效果

### 修复前
- ✗ 设置静默后仍收到告警通知
- ✗ 历史告警会继续发送通知
- ✗ 静默功能不完整

### 修复后
- ✓ 静默期内不发送任何告警通知
- ✓ 静默期内不发送恢复通知
- ✓ 静默过期后自动清除配置
- ✓ 日志记录跳过的告警

## 验证方法

### 1. 运行测试脚本

```bash
PYTHONPATH=/Users/william/prog2/temp/smartdba python test_notification_silence.py
```

### 2. 手动验证

1. 设置数据源静默
2. 等待30秒（通知分发器周期）
3. 检查日志，应该看到：
   ```
   Skipping alert XXX: datasource YYY is silenced
   ```
4. 确认不收到飞书通知

### 3. 验证自动恢复

1. 等待静默期结束
2. 通知分发器自动清除静默配置
3. 恢复发送告警通知

## 完整的静默保护机制

现在系统在三个层面实现了静默保护：

### 1. 指标采集层
- `metric_collector.py` - 静默期内不采集指标
- 避免产生新的指标数据

### 2. 告警创建层
- `metric_collector.py` - 静默期内不创建新告警
- `_check_thresholds_and_trigger()` - 跳过阈值检查
- `_handle_connection_failure()` - 跳过连接失败告警

### 3. 通知发送层（本次修复）
- `notification_dispatcher.py` - 静默期内不发送通知
- 包括告警通知和恢复通知
- 即使是历史告警也不会发送

## 注意事项

1. **历史告警**: 静默前创建的告警在静默期内也不会发送通知
2. **恢复通知**: 静默期内告警恢复也不会发送通知
3. **自动清除**: 静默过期后自动清除配置，无需手动操作
4. **日志记录**: 所有跳过的告警都会记录在日志中

## 相关文件

- `backend/services/notification_dispatcher.py` - 通知分发器（已修复）
- `test_notification_silence.py` - 测试脚本

## 部署说明

修复已完成，需要重启应用以应用更改：

```bash
# 重启应用
python run.py
```

重启后，静默功能将完整生效，静默期内不会收到任何告警通知。
