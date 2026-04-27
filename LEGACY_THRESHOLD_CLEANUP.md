# 旧单层阈值格式清理说明

## 清理概述

本次清理移除了系统中对旧单层阈值格式的支持，统一使用多层级阈值格式。

## 修改文件列表

### 1. `backend/routers/metrics.py`
- 移除 `_build_threshold_health` 函数中的旧单层阈值兼容代码
- 只保留多层级阈值检查逻辑
- 无效格式（缺少 `levels` 数组）会被跳过

**修改前**：
```python
if "levels" in rule and isinstance(rule["levels"], list):
    # 多层级逻辑
else:
    # 旧单层阈值逻辑
    threshold = rule.get("threshold")
    if threshold is None:
        continue
    # ...
```

**修改后**：
```python
if "levels" not in rule or not isinstance(rule["levels"], list):
    continue  # 跳过无效格式

# 只处理多层级格式
# ...
```

### 2. `backend/services/alert_template_service.py`
- 修改 `_validate_multi_level_threshold` 函数
- 强制要求配置必须包含 `levels` 数组
- 缺少 `levels` 时抛出 `ValueError` 而不是返回原始配置

**修改前**：
```python
if "levels" not in rule or not isinstance(rule["levels"], list):
    return rule  # 兼容旧格式
```

**修改后**：
```python
if "levels" not in rule or not isinstance(rule["levels"], list):
    raise ValueError(f"Metric '{metric_name}': must have 'levels' array configuration")
```

### 3. `backend/services/threshold_checker.py`
- 移除冷却期内错误使用 `async with` 的代码
- 修复语法错误

### 4. `backend/models/inspection_config.py`
- 更新 `threshold_rules` 字段的注释示例
- 只展示多层级格式

### 5. `tests/test_multi_level_threshold_health.py`
- 移除旧单层阈值测试用例 `test_legacy_single_level_threshold`
- 新增无效格式跳过测试 `test_invalid_threshold_format_skipped`
- 保留所有多层级阈值测试（6 个测试用例全部通过）

## 格式对比

### 旧格式（已废弃）
```json
{
  "disk_usage": {
    "threshold": 90,
    "duration": 60
  }
}
```

### 新格式（唯一支持）
```json
{
  "disk_usage": {
    "levels": [
      {"severity": "low", "threshold": 80, "duration": 60},
      {"severity": "medium", "threshold": 85, "duration": 60},
      {"severity": "high", "threshold": 90, "duration": 60},
      {"severity": "critical", "threshold": 95, "duration": 60}
    ]
  }
}
```

## 数据库检查结果

✅ 检查了 154 个巡检配置，**所有配置都已使用多层级格式**，无需数据迁移。

## 影响评估

### 正面影响
1. **代码简化**：移除了大量兼容代码，逻辑更清晰
2. **一致性**：告警触发和健康检查使用相同的格式
3. **可维护性**：只需维护一套阈值逻辑
4. **功能增强**：多层级格式支持更细粒度的告警控制

### 潜在风险
1. **API 兼容性**：如果外部系统通过 API 提交旧格式配置，会被拒绝
2. **手动配置**：用户手动编辑配置时必须使用新格式

### 风险缓解
1. 所有内置告警模板已使用新格式
2. 数据库中无旧格式配置
3. 验证逻辑会明确提示格式错误
4. 文档已更新为新格式示例

## 测试验证

```bash
python -m pytest tests/test_multi_level_threshold_health.py -v
```

**测试结果**：6 个测试用例全部通过
- ✅ 磁盘使用率 95% 触发 critical 告警
- ✅ 磁盘使用率 85% 触发 high 告警
- ✅ 磁盘使用率 75% 显示健康
- ✅ 多个指标同时超过阈值
- ✅ 未配置阈值时的处理
- ✅ 无效格式被跳过

## 后续建议

1. **监控告警**：观察是否有配置验证失败的日志
2. **用户文档**：更新用户手册，说明阈值配置格式
3. **API 文档**：更新 API 文档中的配置示例
4. **前端界面**：确保前端配置界面只生成新格式

## 相关文档

- [健康状态检查修复说明](./HEALTH_CHECK_FIX.md)
- [多层级阈值配置示例](./backend/models/inspection_config.py)
- [默认告警模板](./backend/services/alert_template_service.py)
