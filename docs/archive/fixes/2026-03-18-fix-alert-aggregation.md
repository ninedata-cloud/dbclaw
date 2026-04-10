# 告警聚合时间配置修复

**日期**: 2026-03-18
**问题**: 每1小时收到相同的告警通知

## 问题分析

### 原因

1. **聚合引擎使用 `sent_at` 字段判断** - 但该字段在发送失败时为 `None`
2. **原聚合窗口为10分钟** - 太短，导致频繁通知
3. **发送日志记录不完整** - `sent_at` 字段未正确设置

### 修复方案

#### 1. 修改聚合窗口为60分钟

从10分钟改为60分钟，减少重复通知：

```python
cutoff_time = datetime.now() - timedelta(minutes=60)  # 从10改为60
```

#### 2. 使用 `created_at` 而不是 `sent_at`

因为 `sent_at` 可能为 `None`，改用 `created_at` 判断：

```python
# 修改前
AlertDeliveryLog.status == "sent",
AlertDeliveryLog.sent_at >= cutoff_time,

# 修改后
AlertDeliveryLog.created_at >= cutoff_time,  # 使用 created_at
```

#### 3. 移除 `status == "sent"` 条件

即使发送失败，也应该计入聚合窗口，避免重复尝试：

```python
# 修改前：只统计成功发送的
AlertDeliveryLog.status == "sent",

# 修改后：统计所有尝试（包括失败的）
# 移除此条件
```

## 修复效果

### 修复前
- ✗ 每10分钟尝试发送一次
- ✗ 发送失败后立即重试
- ✗ 导致频繁的重复通知

### 修复后
- ✓ 每60分钟最多发送一次
- ✓ 即使发送失败也计入聚合窗口
- ✓ 大幅减少重复通知

## 聚合规则说明

### 默认聚合规则

相同数据源 + 相同告警类型，在 **60分钟** 内只发送一次通知。

例如：
- 数据源A的连接失败告警
- 第1次：立即发送
- 第2次（10分钟后）：被抑制
- 第3次（30分钟后）：被抑制
- 第4次（65分钟后）：发送

### 自定义聚合规则

如果需要更灵活的聚合策略，可以在告警订阅中配置自定义聚合脚本。

## 配置选项

### 方式1: 修改代码（已完成）

在 `backend/services/aggregation_engine.py` 中：

```python
cutoff_time = datetime.now() - timedelta(minutes=60)  # 聚合窗口
```

### 方式2: 通过配置文件（未实现）

可以在 `.env` 中添加：

```bash
ALERT_AGGREGATION_WINDOW_MINUTES=60
```

然后在代码中读取配置。

## 验证方法

### 1. 重启应用

```bash
python run.py
```

### 2. 观察日志

查看聚合引擎的日志：

```
Suppressing alert XXX due to recent delivery (datasource=YYY, type=ZZZ, found N deliveries in last 60 minutes)
```

### 3. 验证通知频率

- 触发一个持续的告警（如连接失败）
- 确认60分钟内只收到1次通知
- 60分钟后如果告警仍存在，会再次通知

## 建议

### 1. 修复通知发送

如果通知一直发送失败（status=failed），应该：
1. 检查 Webhook URL 是否正确
2. 检查钉钉配置是否正确
3. 检查网络连接

### 2. 调整聚合窗口

根据实际需求调整聚合窗口：
- **紧急告警**: 30分钟
- **一般告警**: 60分钟（当前设置）
- **低优先级**: 120分钟

### 3. 使用自定义聚合脚本

对于特殊场景，可以编写自定义聚合脚本，例如：
- 工作时间内更频繁通知
- 非工作时间降低频率
- 根据告警严重程度调整频率

## 相关文件

- `backend/services/aggregation_engine.py` - 聚合引擎（已修复）
- `backend/config.py` - 配置文件
- `backend/models/alert_delivery_log.py` - 发送日志模型

## 部署

修复已完成，重启应用即可生效：

```bash
python run.py
```

重启后，相同告警在60分钟内只会发送一次通知。
