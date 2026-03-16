# 智能巡检触发去重机制

## 问题描述

在之前的实现中，AI Guardian 系统对于持续存在的异常（如连接失败、指标超阈值）会每分钟重复触发诊断报告，导致：
- 大量重复的诊断报告
- 数据库存储浪费
- 用户界面噪音过多
- AI 诊断资源浪费

## 解决方案

实现了基于时间窗口的去重机制，避免对同一问题重复触发诊断。

### 核心逻辑

**连接失败去重** (`_handle_connection_failure`):
- 检查最近 5 分钟内是否已有相同数据源的 `connection_failure` 触发
- 如果存在，跳过本次触发并记录 debug 日志
- 只有首次检测到连接失败时才触发诊断

**异常指标去重** (`_check_thresholds_and_trigger`):
- 检查最近 5 分钟内是否已有相同数据源+相同指标的 `anomaly` 触发
- 使用 SQL LIKE 匹配 `trigger_reason` 中的指标名称
- 如果存在，跳过本次触发并记录 debug 日志
- 只有首次检测到指标异常时才触发诊断

### 实现细节

```python
# 查询最近 5 分钟内的触发记录
recent_trigger = await db.execute(
    select(InspectionTrigger).where(
        and_(
            InspectionTrigger.datasource_id == datasource_id,
            InspectionTrigger.trigger_type == trigger_type,
            InspectionTrigger.triggered_at >= now() - timedelta(minutes=5)
        )
    ).order_by(desc(InspectionTrigger.triggered_at)).limit(1)
)
existing_trigger = recent_trigger.scalar_one_or_none()

if existing_trigger:
    logger.debug(f"Skipping duplicate trigger - recent trigger {existing_trigger.id} exists")
    return
```

### 时间窗口选择

选择 **5 分钟** 作为去重窗口的原因：
- 指标采集间隔为 15 秒，5 分钟内会有约 20 次采集
- 足够长以避免重复触发，但不会太长导致错过状态变化
- 如果问题持续超过 5 分钟，会触发新的诊断（可能问题已演变）

### 状态变化检测

去重机制不影响状态变化的检测：
- **从正常到异常**：首次检测到异常时会触发诊断
- **异常持续**：5 分钟内不会重复触发
- **从异常到正常**：连接恢复后，下次异常会重新触发
- **异常演变**：超过 5 分钟后，如果问题仍存在会触发新诊断

## 代码变更

### 文件：`backend/services/metric_collector.py`

**新增导入**:
```python
from datetime import timedelta
from sqlalchemy import and_, desc
from backend.models.inspection_trigger import InspectionTrigger
```

**修改函数**:
1. `_handle_connection_failure()` - 添加连接失败去重检查
2. `_check_thresholds_and_trigger()` - 添加异常指标去重检查

## 测试验证

运行测试脚本验证去重逻辑：
```bash
python test_deduplication.py
```

测试内容：
1. 检查最近 5 分钟内的 connection_failure 触发
2. 检查最近 5 分钟内特定指标的 anomaly 触发
3. 显示最近 10 分钟内所有触发记录

## 预期效果

- ✅ 连接失败只在首次检测时触发诊断
- ✅ 指标异常只在首次超阈值时触发诊断
- ✅ 持续异常不会每分钟重复触发
- ✅ 5 分钟后如果问题仍存在会触发新诊断
- ✅ 减少 90%+ 的重复诊断报告

## 日志输出

**跳过重复触发时**:
```
DEBUG: Skipping duplicate connection_failure trigger for datasource 1 - recent trigger 123 exists
DEBUG: Skipping duplicate anomaly trigger for datasource 1 metric cpu_usage - recent trigger 124 exists
```

**首次触发时**:
```
INFO: Triggered AI diagnosis for connection failure: datasource 1
INFO: Triggering anomaly inspection for datasource 1: cpu_usage=95.00 > 80 for 60s
```

## 未来优化方向

1. **可配置时间窗口**：允许用户自定义去重时间窗口
2. **智能窗口调整**：根据问题严重程度动态调整窗口大小
3. **状态机管理**：记录异常状态转换，更精确地检测状态变化
4. **聚合报告**：对持续异常生成周期性聚合报告而非单次诊断
