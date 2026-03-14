# 异常触发诊断 - 快速开始

## 功能说明

系统现在支持根据配置的阈值自动检测数据库指标异常，并自动触发AI诊断报告生成。

## 快速配置

### 1. 查看当前配置

```bash
curl http://localhost:8000/api/inspections/config/1
```

### 2. 配置阈值规则

```bash
curl -X PUT http://localhost:8000/api/inspections/config/1 \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "schedule_interval": 86400,
    "use_ai_analysis": true,
    "threshold_rules": {
      "cpu_usage": {
        "threshold": 80,
        "duration": 60
      },
      "memory_usage": {
        "threshold": 85,
        "duration": 60
      },
      "disk_usage": {
        "threshold": 80,
        "duration": 300
      }
    }
  }'
```

### 3. 查看异常触发的报告

```bash
# 查看所有异常触发的报告
curl "http://localhost:8000/api/inspections/reports?trigger_type=anomaly&limit=10"

# 查看特定数据源的异常报告
curl "http://localhost:8000/api/inspections/reports?datasource_id=1&trigger_type=anomaly"
```

### 4. 查看报告详情

```bash
curl http://localhost:8000/api/inspections/reports/detail/{report_id}
```

## 工作原理

1. **指标采集**: 系统每15秒采集一次数据库指标
2. **阈值检查**: 每次采集后自动检查是否超过配置的阈值
3. **持续时间跟踪**: 只有当指标持续超过阈值达到配置的时间后才触发
4. **自动触发**: 触发后自动创建巡检任务并生成AI诊断报告
5. **冷却期**: 触发后1小时内不会重复触发同一指标

## 配置参数说明

### threshold_rules 配置

```json
{
  "metric_name": {
    "threshold": 数值,      // 阈值
    "duration": 秒数        // 持续时间（秒）
  }
}
```

### 支持的指标

| 指标名称 | 说明 | 推荐阈值 |
|---------|------|---------|
| `cpu_usage` | CPU使用率（%） | 80-90 |
| `memory_usage` | 内存使用率（%） | 85-90 |
| `disk_usage` | 磁盘使用率（%） | 80-85 |
| `connections` | 活跃连接数 | 根据业务调整 |

## 示例场景

### 场景1: CPU持续高负载

```
09:00:00  CPU=75%   正常
09:00:15  CPU=85%   超过阈值(80%)，开始跟踪
09:00:30  CPU=87%   持续15秒
09:00:45  CPU=90%   持续30秒
09:01:00  CPU=92%   持续45秒
09:01:15  CPU=95%   持续60秒 → 触发巡检！
09:01:30  生成报告: "cpu_usage=95.00 > 80 for 60s"
```

### 场景2: 短暂波动不触发

```
09:00:00  CPU=75%   正常
09:00:15  CPU=85%   超过阈值，开始跟踪
09:00:30  CPU=70%   恢复正常，清除跟踪
09:00:45  CPU=75%   正常
```

不会触发，因为没有持续超过60秒。

## 测试验证

运行测试脚本验证功能：

```bash
python test_anomaly_trigger.py
```

## 监控日志

查看服务器日志中的阈值检查信息：

```bash
tail -f server.log | grep -i "threshold\|violation\|trigger"
```

日志示例：
```
Threshold violation started for datasource 1: cpu_usage=95.5 > 80
Threshold violation trigger for datasource 1: cpu_usage=95.5 > 80 for 120s
Triggering anomaly inspection for datasource 1: cpu_usage=95.50 > 80 for 120.5s
```

## 常见问题

### Q: 为什么配置了阈值但没有触发？

A: 检查以下几点：
1. `InspectionConfig.enabled` 是否为 `true`
2. 指标是否真的持续超过阈值达到配置的 `duration`
3. 是否在冷却期内（触发后1小时内不会重复触发）
4. 查看日志确认指标采集是否正常

### Q: 如何调整触发的敏感度？

A: 调整两个参数：
- `threshold`: 降低阈值会更容易触发
- `duration`: 减少持续时间会更快触发

例如，测试环境可以设置：
```json
{
  "cpu_usage": {"threshold": 70, "duration": 30}
}
```

### Q: 如何禁用异常触发？

A: 两种方式：
1. 设置 `enabled: false` 禁用整个巡检功能
2. 设置 `threshold_rules: {}` 清空所有阈值规则

### Q: 冷却期可以调整吗？

A: 当前冷却期固定为1小时（3600秒），在 `ThresholdChecker` 类中定义。如需调整，修改：
```python
self._trigger_cooldown = 3600  # 改为需要的秒数
```

## 下一步

1. 根据实际业务调整阈值配置
2. 观察触发频率，优化 `duration` 参数
3. 查看生成的报告，评估AI诊断质量
4. 考虑集成通知系统（邮件/钉钉/企业微信）

## 相关文档

- `ANOMALY_TRIGGER_IMPLEMENTATION.md` - 完整实现文档
- `AUTO_INSPECTION_LOGIC.md` - 自动巡检逻辑说明
- `TIMEOUT_FIX_SUMMARY.md` - SSH超时修复说明
