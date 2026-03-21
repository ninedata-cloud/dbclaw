# 告警频繁发送问题修复

**日期**: 2026-03-19
**问题**: 告警聚合逻辑未生效，导致相同告警频繁发送
**状态**: ✅ 已修复

## 问题描述

用户报告告警频繁发送，聚合逻辑没有生效。经过分析发现以下问题：

1. **事件聚合失效** - 每个告警都创建了独立的事件，没有聚合到同一个事件中
2. **通知重复发送** - 同一个告警被多次发送通知
3. **聚合检查不准确** - 聚合引擎的检查逻辑存在问题

## 根本原因分析

### 1. 事件聚合问题

在 `alert_event_service.py` 的 `_find_matching_event` 方法中，查找匹配事件时没有过滤已解决的事件：

```python
# ❌ 问题代码：会匹配到已解决的事件
result = await db.execute(
    select(AlertEvent)
    .where(
        and_(
            AlertEvent.aggregation_key == aggregation_key,
            AlertEvent.event_end_time >= time_threshold
        )
    )
    .order_by(AlertEvent.event_end_time.desc())
    .limit(1)
)
```

这导致：
- 如果最近的事件已经被解决，新告警仍然会创建新事件
- 无法正确聚合到活跃的事件中

### 2. 聚合检查逻辑问题

在 `aggregation_engine.py` 的 `_default_aggregation_rule` 方法中：

```python
# ❌ 问题代码：使用 created_at 而不是 sent_at
result = await db.execute(
    select(AlertDeliveryLog).join(
        AlertMessage, AlertDeliveryLog.alert_id == AlertMessage.id
    ).where(
        and_(
            AlertDeliveryLog.subscription_id == subscription.id,
            AlertDeliveryLog.created_at >= cutoff_time,  # 应该用 sent_at
            AlertMessage.datasource_id == alert.datasource_id,
            AlertMessage.alert_type == alert.alert_type
        )
    )
)
```

问题：
- 没有检查告警是否属于同一个事件
- 没有过滤投递状态（应该只检查成功发送的）
- 使用 `created_at` 而不是 `sent_at`

## 解决方案

### 1. 修复事件聚合逻辑

在 `alert_event_service.py` 中，只匹配活跃或已确认的事件：

```python
# ✅ 修复后：只匹配未解决的事件
result = await db.execute(
    select(AlertEvent)
    .where(
        and_(
            AlertEvent.aggregation_key == aggregation_key,
            AlertEvent.event_end_time >= time_threshold,
            AlertEvent.status.in_(["active", "acknowledged"])  # 只匹配未解决的事件
        )
    )
    .order_by(AlertEvent.event_end_time.desc())
    .limit(1)
)
```

### 2. 改进聚合检查逻辑

在 `aggregation_engine.py` 中，优先基于事件进行聚合：

```python
# ✅ 修复后：基于事件的聚合
if alert.event_id:
    # 查询该事件的所有告警的投递记录
    result = await db.execute(
        select(AlertDeliveryLog).join(
            AlertMessage, AlertDeliveryLog.alert_id == AlertMessage.id
        ).where(
            and_(
                AlertDeliveryLog.subscription_id == subscription.id,
                AlertMessage.event_id == alert.event_id,
                AlertDeliveryLog.status == "sent"
            )
        )
    )
    event_deliveries = result.scalars().all()

    if event_deliveries:
        logger.info(
            f"Suppressing alert {alert.id} - event {alert.event_id} already has "
            f"{len(event_deliveries)} notifications sent"
        )
        return False
```

如果没有事件ID，则使用时间窗口聚合：

```python
# 使用60分钟聚合窗口
cutoff_time = datetime.now() - timedelta(minutes=60)

result = await db.execute(
    select(AlertDeliveryLog).join(
        AlertMessage, AlertDeliveryLog.alert_id == AlertMessage.id
    ).where(
        and_(
            AlertDeliveryLog.subscription_id == subscription.id,
            AlertDeliveryLog.sent_at >= cutoff_time,
            AlertDeliveryLog.status == "sent",  # 只检查成功发送的
            AlertMessage.datasource_id == alert.datasource_id,
            AlertMessage.alert_type == alert.alert_type
        )
    )
)
```

## 修改的文件

1. **backend/services/alert_event_service.py**
   - 修改 `_find_matching_event` 方法
   - 添加事件状态过滤

2. **backend/services/aggregation_engine.py**
   - 修改 `_default_aggregation_rule` 方法
   - 优先基于事件进行聚合
   - 改进时间窗口聚合逻辑

## 聚合逻辑说明

### 两层聚合机制

1. **事件层聚合** (alert_event_service.py)
   - 相同数据源 + 相同指标/类型的告警聚合到同一个事件
   - 时间窗口：5分钟（可配置）
   - 只聚合到活跃或已确认的事件

2. **通知层聚合** (aggregation_engine.py)
   - 同一个事件只发送一次通知
   - 如果没有事件，使用60分钟时间窗口
   - 只检查成功发送的通知

### 聚合流程

```
新告警产生
    ↓
查找匹配的活跃事件
    ↓
找到？ → 是 → 添加到现有事件
    ↓
    否
    ↓
创建新事件
    ↓
检查该事件是否已发送通知
    ↓
已发送？ → 是 → 抑制通知
    ↓
    否
    ↓
发送通知
```

## 配置参数

### 事件聚合时间窗口

在 `backend/config.py` 中配置：

```python
ALERT_AGGREGATION_TIME_WINDOW_MINUTES = 5  # 默认5分钟
```

### 通知聚合时间窗口

在 `aggregation_engine.py` 中硬编码为 60 分钟。

## 测试验证

### 测试脚本

```bash
python test_aggregation_logic.py
```

### 预期结果

1. **事件聚合正常**
   - 相同类型的告警应该聚合到同一个事件
   - 事件的 `alert_count` 应该大于 1

2. **通知不重复**
   - 同一个事件只发送一次通知
   - 后续告警被抑制

3. **日志输出**
   - 看到 "Suppressing alert X - event Y already has Z notifications sent"
   - 看到 "Suppressing alert X due to recent delivery"

## 监控指标

可以通过以下指标监控聚合效果：

1. **事件聚合率** = 总告警数 / 总事件数
   - 理想值：> 2（平均每个事件包含2个以上告警）

2. **通知抑制率** = 抑制的通知数 / 总告警数
   - 理想值：> 50%（至少一半的告警被抑制）

3. **平均事件持续时间**
   - 理想值：< 10分钟（快速聚合和解决）

## 常见问题

### Q1: 为什么有些告警没有被聚合？

A: 可能的原因：
- 告警类型不同（metric_name 或 alert_type 不同）
- 数据源不同
- 超过时间窗口（5分钟）
- 之前的事件已经被解决

### Q2: 为什么同一个告警被发送多次？

A: 可能的原因：
- 订阅配置了多个通知渠道（这是正常的）
- 聚合逻辑被自定义脚本覆盖
- 投递失败后重试

### Q3: 如何调整聚合时间窗口？

A: 修改 `backend/config.py` 中的 `ALERT_AGGREGATION_TIME_WINDOW_MINUTES`

## 后续优化建议

1. **动态时间窗口** - 根据告警频率自动调整聚合窗口
2. **智能聚合** - 使用机器学习识别相关告警
3. **聚合策略配置** - 允许用户自定义聚合策略
4. **聚合效果监控** - 添加聚合效果的可视化监控

## 总结

通过修复事件聚合逻辑和改进通知聚合检查，成功解决了告警频繁发送的问题。现在系统能够：

1. ✅ 正确聚合相同类型的告警到同一个事件
2. ✅ 同一个事件只发送一次通知
3. ✅ 使用时间窗口防止重复通知
4. ✅ 只匹配活跃的事件进行聚合

这大大减少了告警噪音，提升了用户体验。
