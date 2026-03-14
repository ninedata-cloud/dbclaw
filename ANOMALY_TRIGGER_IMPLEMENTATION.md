# 异常触发诊断报告功能实现

## 概述

实现了完整的异常触发诊断报告逻辑，系统现在可以根据配置的阈值自动检测指标异常并触发巡检报告生成。

## 核心组件

### 1. ThresholdChecker（阈值检查器）
**文件**: `backend/services/threshold_checker.py`

负责监控指标并跟踪违规持续时间。

**主要功能**:
- 跟踪每个数据源的指标违规开始时间
- 计算违规持续时间
- 当违规持续时间超过配置的阈值时触发巡检
- 防止重复触发（1小时冷却期）
- 支持多种指标名称映射（如 `cpu_usage`, `cpu.usage_percent`, `cpu_percent`）

**关键方法**:
```python
def check_thresholds(
    datasource_id: int,
    metrics: Dict[str, Any],
    threshold_rules: Dict[str, Dict[str, float]]
) -> List[Dict[str, Any]]
```

**工作流程**:
1. 检查每个配置的阈值规则
2. 提取当前指标值
3. 判断是否超过阈值
4. 如果超过，记录违规开始时间
5. 计算违规持续时间
6. 如果持续时间 >= 配置的duration，触发巡检
7. 检查冷却期，避免重复触发
8. 如果指标恢复正常，清除违规记录

### 2. MetricCollector 集成
**文件**: `backend/services/metric_collector.py`

在指标采集后自动检查阈值。

**修改内容**:
```python
# 导入 ThresholdChecker
from backend.services.threshold_checker import ThresholdChecker

# 创建全局实例
_threshold_checker = ThresholdChecker()

# 在 collect_metrics_for_connection 中添加阈值检查
await _check_thresholds_and_trigger(db, datasource_id, normalized_status)
```

**阈值检查函数**:
```python
async def _check_thresholds_and_trigger(db, datasource_id: int, metrics: Dict[str, Any]):
    """Check if metrics violate thresholds and trigger inspection if needed"""
    # 1. 获取数据源的巡检配置
    config = await db.execute(
        select(InspectionConfig).where(
            InspectionConfig.datasource_id == datasource_id,
            InspectionConfig.enabled == True
        )
    )
    
    # 2. 检查阈值
    violations = _threshold_checker.check_thresholds(
        datasource_id, metrics, config.threshold_rules
    )
    
    # 3. 对每个违规触发巡检
    for violation in violations:
        await _inspection_service.trigger_inspection(
            db=db,
            datasource_id=datasource_id,
            trigger_type="anomaly",
            reason=f"{metric_name}={value} > {threshold} for {duration}s",
            metric_snapshot={...}
        )
```

### 3. InspectionService 更新
**文件**: `backend/services/inspection_service.py`

添加了 `metric_snapshot` 参数支持。

**修改内容**:
```python
async def trigger_inspection(
    self, db: AsyncSession, datasource_id: int,
    trigger_type: str, reason: str = None,
    metric_snapshot: Dict[str, Any] = None  # 新增参数
) -> int:
    trigger = InspectionTrigger(
        datasource_id=datasource_id,
        trigger_type=trigger_type,
        trigger_reason=reason,
        metric_snapshot=metric_snapshot,  # 保存触发时的指标快照
        processed=False
    )
    # ...
```

## 配置说明

### 阈值规则配置

通过 `InspectionConfig.threshold_rules` 配置：

```json
{
  "cpu_usage": {
    "threshold": 80,      // 阈值：80%
    "duration": 60        // 持续时间：60秒
  },
  "memory_usage": {
    "threshold": 85,
    "duration": 60
  },
  "disk_usage": {
    "threshold": 80,
    "duration": 300       // 5分钟
  },
  "connections": {
    "threshold": 100,
    "duration": 120       // 2分钟
  }
}
```

### 默认配置

系统为每个数据源创建默认配置：
- CPU使用率：80%，持续60秒
- 内存使用率：85%，持续60秒
- 磁盘使用率：80%，持续300秒
- 连接数：100，持续120秒

### 支持的指标名称

ThresholdChecker 支持多种指标名称格式：

| 配置名称 | 支持的实际指标名称 |
|---------|------------------|
| `cpu_usage` | `cpu_usage_percent`, `cpu.usage_percent`, `cpu_percent` |
| `memory_usage` | `memory_usage_percent`, `memory.usage_percent`, `mem_percent` |
| `disk_usage` | `disk_usage_percent`, `disk.usage_percent`, `disk_percent` |
| `connections` | `active_connections`, `connection_count`, `threads_connected` |

也支持嵌套路径，如 `cpu.usage_percent`。

## 工作流程

### 完整流程图

```
MetricCollector (每15秒)
    ↓
采集数据源指标
    ↓
标准化指标 (MetricNormalizer)
    ↓
保存到 MetricSnapshot
    ↓
_check_thresholds_and_trigger()
    ↓
查询 InspectionConfig (enabled=True)
    ↓
ThresholdChecker.check_thresholds()
    ↓
检查每个阈值规则：
  - cpu_usage > 80 ?
  - memory_usage > 85 ?
  - disk_usage > 80 ?
  - connections > 100 ?
    ↓
如果超过阈值：
  - 记录违规开始时间
  - 计算违规持续时间
    ↓
如果持续时间 >= 配置的duration：
  - 检查冷却期（1小时）
  - 如果不在冷却期：
      ↓
      触发巡检！
      ↓
      InspectionService.trigger_inspection(type='anomaly')
      ↓
      创建 InspectionTrigger 记录
      ↓
      异步生成 AI 诊断报告
      ↓
      更新 InspectionTrigger (processed=True, report_id=X)
```

### 时间线示例

假设 CPU 使用率阈值为 80%，持续时间为 60 秒：

```
00:00:00  CPU=75%  正常
00:00:15  CPU=85%  违规开始，记录开始时间
00:00:30  CPU=87%  违规持续 15秒，未达到 60秒
00:00:45  CPU=90%  违规持续 30秒，未达到 60秒
00:01:00  CPU=92%  违规持续 45秒，未达到 60秒
00:01:15  CPU=95%  违规持续 60秒，触发巡检！
00:01:30  CPU=93%  冷却期内，不再触发
00:02:00  CPU=70%  恢复正常，清除违规记录
```

## API 使用

### 1. 查看巡检配置

```bash
GET /api/inspections/config/{datasource_id}
```

响应：
```json
{
  "id": 1,
  "datasource_id": 1,
  "enabled": true,
  "schedule_interval": 86400,
  "use_ai_analysis": true,
  "ai_model_id": null,
  "kb_ids": [],
  "threshold_rules": {
    "cpu_usage": {"threshold": 80, "duration": 60},
    "memory_usage": {"threshold": 85, "duration": 60},
    "disk_usage": {"threshold": 80, "duration": 300}
  },
  "last_scheduled_at": "2026-03-14T12:00:00",
  "next_scheduled_at": "2026-03-15T12:00:00"
}
```

### 2. 更新阈值配置

```bash
PUT /api/inspections/config/{datasource_id}
Content-Type: application/json

{
  "enabled": true,
  "schedule_interval": 86400,
  "use_ai_analysis": true,
  "threshold_rules": {
    "cpu_usage": {"threshold": 90, "duration": 120},
    "memory_usage": {"threshold": 90, "duration": 120}
  }
}
```

### 3. 查看巡检历史

```bash
GET /api/inspections/reports?datasource_id=1&trigger_type=anomaly&limit=10
```

响应：
```json
{
  "reports": [
    {
      "report_id": 123,
      "datasource_name": "Production MySQL",
      "title": "Anomaly Inspection - Production MySQL",
      "trigger_type": "anomaly",
      "trigger_reason": "cpu_usage=95.50 > 80 for 120s",
      "created_at": "2026-03-14T12:30:00",
      "status": "completed"
    }
  ],
  "total": 1
}
```

### 4. 查看报告详情

```bash
GET /api/inspections/reports/detail/{report_id}
```

## 测试验证

运行测试脚本：
```bash
python test_anomaly_trigger.py
```

测试覆盖：
- ✓ 阈值超过后持续时间检测
- ✓ 触发后的冷却期机制
- ✓ 指标恢复正常后清除违规记录
- ✓ 多个指标同时超过阈值
- ✓ 不同指标名称格式的映射
- ✓ 配置API的读取和创建

## 特性

### 1. 智能持续时间检测
不会因为瞬时波动触发，必须持续超过配置的时间才触发。

### 2. 冷却期机制
触发后1小时内不会重复触发同一指标，避免报告轰炸。

### 3. 灵活的指标映射
支持多种指标名称格式，兼容不同数据库的指标输出。

### 4. 完整的审计追踪
每次触发都记录在 `InspectionTrigger` 表中，包含：
- 触发类型（anomaly）
- 触发原因（具体的指标和值）
- 指标快照（触发时的完整指标数据）
- 生成的报告ID

### 5. 异步报告生成
触发后异步生成报告，不阻塞指标采集流程。

## 配置建议

### 生产环境推荐配置

```json
{
  "cpu_usage": {
    "threshold": 85,
    "duration": 300      // 5分钟，避免短暂波动
  },
  "memory_usage": {
    "threshold": 90,
    "duration": 300
  },
  "disk_usage": {
    "threshold": 85,
    "duration": 600      // 10分钟，磁盘增长较慢
  },
  "connections": {
    "threshold": 200,    // 根据实际业务调整
    "duration": 180      // 3分钟
  }
}
```

### 测试环境配置

```json
{
  "cpu_usage": {
    "threshold": 70,
    "duration": 60       // 更敏感，快速发现问题
  },
  "memory_usage": {
    "threshold": 75,
    "duration": 60
  }
}
```

## 监控和调试

### 查看违规状态

可以通过 ThresholdChecker 的 `get_violation_status()` 方法查看当前违规状态：

```python
status = _threshold_checker.get_violation_status(datasource_id)
# 返回：
# {
#   "cpu_usage": {
#     "violation_start": "2026-03-14T12:30:00",
#     "violation_duration": 45.5,
#     "last_trigger": "2026-03-14T11:30:00"
#   }
# }
```

### 日志输出

系统会记录详细的日志：
- 违规开始：`Threshold violation started for datasource X: cpu_usage=95.5 > 80`
- 违规结束：`Threshold violation ended for datasource X: cpu_usage=75 <= 80 (was violated for 120s)`
- 触发巡检：`Threshold violation trigger for datasource X: cpu_usage=95.5 > 80 for 120s`
- 冷却期跳过：`Skipping trigger for cpu_usage on datasource X: in cooldown period (1800s < 3600s)`

## 相关文件

- `backend/services/threshold_checker.py` - 阈值检查器核心逻辑
- `backend/services/metric_collector.py` - 指标采集和阈值检查集成
- `backend/services/inspection_service.py` - 巡检服务（添加 metric_snapshot 支持）
- `backend/models/inspection_config.py` - 巡检配置模型
- `backend/models/inspection_trigger.py` - 巡检触发记录模型
- `backend/routers/inspections.py` - 巡检配置API
- `test_anomaly_trigger.py` - 功能测试脚本

## 未来改进

1. **自适应阈值**: 基于历史数据自动学习正常范围
2. **阈值模板**: 预定义不同场景的阈值配置（高负载、低负载、开发环境等）
3. **通知集成**: 触发时发送邮件/钉钉/企业微信通知
4. **趋势分析**: 分析指标趋势，预测即将超过阈值
5. **多维度阈值**: 支持组合条件（如 CPU>80% AND Memory>85%）
