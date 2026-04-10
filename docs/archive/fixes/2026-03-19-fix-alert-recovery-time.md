# 告警事件恢复时间显示问题修复

**日期**: 2026-03-19
**问题**: 告警管理界面显示的开始时间和恢复时间相同
**状态**: ✅ 已修复

## 问题描述

在告警管理界面的"告警列表"标签页中，已解决的事件显示的"开始时间"和"恢复时间"完全相同，都是事件的开始时间。

**示例**：
```
开始时间: 2026/3/18 22:49:32
恢复时间: 2026/3/18 22:49:32  ← 应该显示实际恢复时间
```

## 根本原因

在 `alert_event_service.py` 中，当事件被解决时，只更新了 `status` 和 `last_updated` 字段，但没有更新 `event_end_time` 字段。

### 问题代码

#### 1. `resolve_event` 方法

```python
# ❌ 问题代码
event.status = "resolved"
event.last_updated = datetime.now()
# 缺少：event.event_end_time = datetime.now()
```

#### 2. `check_and_auto_resolve_event` 方法

```python
# ❌ 问题代码
event.status = "resolved"
event.last_updated = datetime.now()
# 缺少：event.event_end_time = datetime.now()
```

## 字段说明

### AlertEvent 模型字段

- **event_start_time**: 事件开始时间（第一个告警的创建时间）
- **event_end_time**: 事件结束时间（最后一个告警的创建时间，或事件解决时间）
- **last_updated**: 最后更新时间（任何字段变更的时间）

### 字段用途

1. **创建事件时**:
   - `event_start_time` = 第一个告警的创建时间
   - `event_end_time` = 第一个告警的创建时间（初始值）

2. **添加告警到事件时**:
   - `event_end_time` = 最新告警的创建时间（更新为最新）

3. **解决事件时**:
   - `event_end_time` = 实际解决时间（**之前缺失**）

## 解决方案

在事件解决时，更新 `event_end_time` 为实际的解决时间。

### 修复代码

#### 1. `resolve_event` 方法

```python
# ✅ 修复后
now = datetime.now()
event.status = "resolved"
event.event_end_time = now  # 更新恢复时间
event.last_updated = now
```

#### 2. `check_and_auto_resolve_event` 方法

```python
# ✅ 修复后
now = datetime.now()
event.status = "resolved"
event.event_end_time = now  # 更新恢复时间
event.last_updated = now
```

## 修改的文件

- **backend/services/alert_event_service.py**
  - 修改 `resolve_event` 方法（第293-294行）
  - 修改 `check_and_auto_resolve_event` 方法（第352-353行）

## 前端显示逻辑

前端代码（`alerts.js`）已经正确实现了显示逻辑：

```javascript
// 第458-460行
const endTime = event.status === 'resolved' && event.event_end_time
    ? new Date(event.event_end_time).toLocaleString('zh-CN')
    : '-';
```

- 如果事件状态是 `resolved` 且有 `event_end_time`，显示恢复时间
- 否则显示 `-`

## 时间线说明

### 修复前

```
事件创建: 2026-03-18 22:49:32
  ↓
告警1: 22:49:32 → event_start_time = 22:49:32, event_end_time = 22:49:32
  ↓
告警2: 22:50:15 → event_end_time = 22:50:15
  ↓
告警3: 22:51:03 → event_end_time = 22:51:03
  ↓
事件解决: 23:15:20 → status = "resolved"
                     event_end_time = 22:51:03 ❌ (未更新)
```

### 修复后

```
事件创建: 2026-03-18 22:49:32
  ↓
告警1: 22:49:32 → event_start_time = 22:49:32, event_end_time = 22:49:32
  ↓
告警2: 22:50:15 → event_end_time = 22:50:15
  ↓
告警3: 22:51:03 → event_end_time = 22:51:03
  ↓
事件解决: 23:15:20 → status = "resolved"
                     event_end_time = 23:15:20 ✅ (正确更新)
```

## 测试验证

### 测试步骤

1. **创建测试告警**
   ```bash
   # 触发一个阈值告警
   ```

2. **等待告警聚合**
   - 观察事件被创建
   - 记录开始时间

3. **解决告警**
   - 在告警管理界面点击"解决"按钮
   - 或等待自动解决

4. **验证时间显示**
   - 开始时间：应该是第一个告警的时间
   - 恢复时间：应该是点击解决的时间（或自动解决的时间）
   - 两个时间应该不同

### 预期结果

```
开始时间: 2026/3/18 22:49:32
恢复时间: 2026/3/18 23:15:20  ✓ 显示实际解决时间
```

## 影响范围

### 受影响的功能

1. **告警管理界面** - 事件列表的恢复时间显示
2. **告警统计** - 事件持续时间计算
3. **告警报表** - 基于恢复时间的统计

### 不受影响的功能

1. **告警创建** - 不涉及解决逻辑
2. **告警通知** - 不依赖恢复时间
3. **告警聚合** - 使用 `event_end_time` 判断时间窗口，但逻辑仍然正确

## 数据修复

对于已经存在的已解决事件，如果需要修复历史数据，可以运行以下 SQL：

```sql
-- 将已解决事件的 event_end_time 更新为 last_updated
UPDATE alert_events
SET event_end_time = last_updated
WHERE status = 'resolved'
  AND event_end_time < last_updated;
```

**注意**: 这只是近似修复，因为 `last_updated` 可能不是精确的解决时间。

## 相关问题

### Q1: 为什么不使用 last_updated 作为恢复时间？

A: `last_updated` 是通用的更新时间字段，任何字段变更都会更新它。而 `event_end_time` 是专门用于表示事件结束时间的字段，语义更明确。

### Q2: event_end_time 在未解决时的含义是什么？

A: 在事件未解决时，`event_end_time` 表示最后一个告警的创建时间，用于判断是否应该将新告警聚合到这个事件中。

### Q3: 如果事件被重新激活，event_end_time 会怎样？

A: 如果事件被重新激活（添加新告警），`event_end_time` 会被更新为新告警的创建时间。

## 后续优化建议

1. **添加 resolved_at 字段** - 专门记录事件解决时间，与 `event_end_time` 分离
2. **记录解决原因** - 记录是手动解决还是自动解决
3. **记录解决人** - 如果是手动解决，记录操作人
4. **事件持续时间统计** - 在前端显示事件持续时间

## 总结

通过在事件解决时更新 `event_end_time` 字段，成功修复了恢复时间显示问题。现在告警管理界面能够正确显示：

- ✅ 开始时间：第一个告警的创建时间
- ✅ 恢复时间：事件实际解决的时间
- ✅ 持续时间：可以通过两个时间计算得出

这使得用户能够准确了解告警事件的完整生命周期。
