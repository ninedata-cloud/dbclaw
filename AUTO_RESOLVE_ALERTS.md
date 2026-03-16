# 告警自动恢复功能

## 概述

SmartDBA 现在支持告警自动恢复功能。当监控指标恢复正常或数据库连接恢复时，系统会自动将相关的活跃告警标记为已解决（resolved）。

## 功能特性

### 1. 阈值告警自动恢复

当监控指标违反阈值时，系统会创建告警。当指标恢复到阈值以下时，系统会自动解除告警。

**工作原理**：
- 每次采集指标时，检查当前指标值
- 查找该数据源的所有活跃阈值告警（status = "active" 或 "acknowledged"）
- 对于每个告警，检查对应的指标是否已恢复正常
- 如果指标值低于配置的阈值，自动调用 `AlertService.resolve_alert()` 解除告警

**示例**：
```
1. CPU 使用率超过 80% → 创建告警（status = "active"）
2. CPU 使用率降至 60% → 自动解除告警（status = "resolved"）
```

### 2. 连接失败告警自动恢复

当数据库连接失败时，系统会创建严重级别的告警。当连接恢复时，系统会自动解除所有连接失败告警。

**工作原理**：
- 每次成功连接数据库时，查找该数据源的所有连接失败告警
- 自动解除所有 `alert_type = "system_error"` 且 `metric_name = "connection_status"` 的活跃告警

**示例**：
```
1. 数据库连接失败 → 创建严重告警（severity = "critical"）
2. 数据库连接恢复 → 自动解除告警（status = "resolved"）
```

## 实现细节

### 核心函数

#### `_auto_resolve_recovered_alerts()`

位置：`backend/services/metric_collector.py`

功能：自动解除已恢复的阈值告警

参数：
- `db`: 数据库会话
- `datasource_id`: 数据源 ID
- `metrics`: 当前指标值字典
- `threshold_rules`: 阈值规则列表
- `current_violations`: 当前违规列表（用于避免解除仍在违规的告警）

逻辑：
1. 查询该数据源的所有活跃阈值告警
2. 构建当前违规指标集合
3. 对于每个告警：
   - 跳过仍在违规的指标
   - 获取当前指标值
   - 查找对应的阈值规则
   - 如果当前值 < 阈值，自动解除告警

#### `_auto_resolve_connection_alerts()`

位置：`backend/services/metric_collector.py`

功能：自动解除连接失败告警

参数：
- `db`: 数据库会话
- `datasource_id`: 数据源 ID

逻辑：
1. 查询该数据源的所有连接失败告警
2. 自动解除所有找到的告警

### 调用时机

#### 阈值告警恢复
在 `_check_thresholds_and_trigger()` 函数中调用：
```python
# Check thresholds
violations = _threshold_checker.check_thresholds(...)

# Auto-resolve alerts for metrics that have recovered
await _auto_resolve_recovered_alerts(db, datasource_id, metrics, threshold_rules, violations)
```

#### 连接告警恢复
在 `collect_metrics_for_connection()` 函数中调用：
```python
try:
    status = await connector.get_status()
    connection_failed = False

    # Auto-resolve connection failure alerts if connection is now successful
    await _auto_resolve_connection_alerts(db, datasource_id)
except Exception as e:
    # Handle connection failure
    ...
```

## 告警状态流转

```
active → acknowledged → resolved
  ↓           ↓            ↑
  └───────────┴────────────┘
     (自动恢复)
```

- **active**: 告警刚创建，未确认
- **acknowledged**: 用户已确认告警，但问题未解决
- **resolved**: 问题已解决（手动或自动）

自动恢复功能会将 `active` 或 `acknowledged` 状态的告警直接更新为 `resolved`。

## 日志记录

系统会记录所有自动恢复操作：

```python
logger.info(
    f"Auto-resolved alert {alert.id}: {alert.metric_name} recovered "
    f"(current={current_value:.2f} < threshold={threshold})"
)

logger.info(f"Auto-resolved connection failure alert {alert.id}: connection restored")
```

## 测试

测试文件：`test_auto_resolve_alerts.py`

测试用例：
1. `test_auto_resolve_recovered_alerts()` - 测试阈值告警自动恢复
2. `test_auto_resolve_connection_alerts()` - 测试连接告警自动恢复
3. `test_no_alerts_to_resolve()` - 测试无告警时的处理

运行测试：
```bash
python test_auto_resolve_alerts.py
```

## 配置

无需额外配置，功能默认启用。

自动恢复依赖于：
- 监控采集周期（默认 15 秒）
- 阈值规则配置（在巡检配置中设置）

## 注意事项

1. **去重保护**：自动恢复不会影响去重逻辑，仍然会避免为同一问题创建重复告警
2. **告警事件**：解除告警时，关联的告警事件（AlertEvent）状态不会自动更新，需要手动管理
3. **通知**：自动解除的告警不会触发通知，只有新创建的告警才会触发通知
4. **性能**：自动恢复检查在每次指标采集时执行，对性能影响很小

## 未来改进

可能的改进方向：
1. 支持恢复延迟（指标恢复 N 分钟后才自动解除告警）
2. 自动更新告警事件状态
3. 为自动恢复的告警发送恢复通知
4. 支持自定义恢复条件（不仅仅是低于阈值）
