# 健康状态检查修复说明

## 问题描述

数据库实例 `ninedata-meta-dev` 磁盘使用率达到 95%，但前端仍然显示"健康"状态（绿色）。

## 根本原因

系统存在两套阈值检查逻辑：

1. **告警触发逻辑**（`backend/services/threshold_checker.py`）
   - 已支持多层级阈值配置（`levels` 数组）
   - 正确识别 95% 超过 90% critical 阈值

2. **健康状态显示逻辑**（`backend/routers/metrics.py`）
   - 只支持旧的单层阈值格式（`{"threshold": 90}`）
   - 不支持新的多层级格式（`{"levels": [...]}`）
   - 当配置是多层级时，`rule.get("threshold")` 返回 `None`，直接跳过检查

## 修复内容

### 1. 更新健康检查逻辑 (`backend/routers/metrics.py`)

**移除旧的单层阈值兼容代码**，只保留多层级阈值支持：

```python
for metric_name, rule in config.threshold_rules.items():
    if "levels" not in rule or not isinstance(rule["levels"], list):
        continue  # 跳过无效格式

    current_value = _extract_metric_value(metrics, metric_name)
    if current_value is None:
        continue

    # 找到被违反的最高严重级别
    sorted_levels = sorted(
        rule["levels"],
        key=lambda x: SEVERITY_ORDER.get(x.get("severity", "low"), 1),
        reverse=True
    )

    for level in sorted_levels:
        threshold = level.get("threshold")
        if threshold is not None and current_value > threshold:
            violations.append({
                "type": "threshold",
                "metric": metric_name,
                "value": current_value,
                "threshold": threshold,
                "severity": level.get("severity", "medium"),
            })
            break
```

### 2. 移除旧单层阈值验证逻辑 (`backend/services/alert_template_service.py`)

修改 `_validate_multi_level_threshold` 函数，**强制要求 `levels` 数组**：

```python
if "levels" not in rule or not isinstance(rule["levels"], list):
    raise ValueError(f"Metric '{metric_name}': must have 'levels' array configuration")
```

之前的代码会在缺少 `levels` 时直接返回原始 rule，现在改为抛出异常。

### 3. 修复语法错误 (`backend/services/threshold_checker.py`)

移除了在非 async 函数中错误使用 `async with` 和 `await` 的代码（第 186-197 行）。

### 4. 更新文档和示例 (`backend/models/inspection_config.py`)

更新 `threshold_rules` 字段的注释示例，只展示多层级格式。

### 5. 更新测试 (`tests/test_multi_level_threshold_health.py`)

- ✅ 移除旧单层阈值测试用例
- ✅ 新增无效格式跳过测试
- ✅ 保留所有多层级阈值测试

所有测试通过（6 个测试用例）。

## 影响范围

- **不再支持旧的单层阈值格式**（`{"threshold": 90, "duration": 60}`）
- **只支持多层级阈值格式**（`{"levels": [...]}`）
- 使用旧格式的配置会被跳过，不会触发告警
- 所有内置告警模板已使用多层级格式

## 多层级阈值格式说明

```json
{
  "metric_name": {
    "levels": [
      {"severity": "low", "threshold": 80, "duration": 60},
      {"severity": "medium", "threshold": 85, "duration": 60},
      {"severity": "high", "threshold": 90, "duration": 60},
      {"severity": "critical", "threshold": 95, "duration": 60}
    ]
  }
}
```

**字段说明**：
- `severity`: 严重级别（low / medium / high / critical）
- `threshold`: 阈值（数值）
- `duration`: 持续时间（秒），0 表示立即触发

**检查逻辑**：
- 从高到低检查严重级别
- 匹配第一个被违反的级别
- 只触发一次（最高级别）

## 默认阈值配置

系统默认的磁盘使用率阈值（来自 `backend/services/alert_template_service.py`）：

```python
"disk_usage": {
    "levels": [
        {"severity": "low", "threshold": 80, "duration": 0},
        {"severity": "medium", "threshold": 85, "duration": 0},
        {"severity": "high", "threshold": 90, "duration": 0},
        {"severity": "critical", "threshold": 95, "duration": 0},
    ]
}
```

修复后，95% 磁盘使用率会正确触发 critical 级别告警并显示为不健康状态。

## 迁移指南

如果数据库中存在旧的单层阈值配置，需要手动迁移为多层级格式：

**旧格式**：
```json
{
  "disk_usage": {"threshold": 90, "duration": 60}
}
```

**新格式**：
```json
{
  "disk_usage": {
    "levels": [
      {"severity": "critical", "threshold": 90, "duration": 60}
    ]
  }
}
```

或使用完整的多层级配置：
```json
{
  "disk_usage": {
    "levels": [
      {"severity": "low", "threshold": 80, "duration": 0},
      {"severity": "medium", "threshold": 85, "duration": 0},
      {"severity": "high", "threshold": 90, "duration": 0},
      {"severity": "critical", "threshold": 95, "duration": 0}
    ]
  }
}
```
