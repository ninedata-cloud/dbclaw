# SmartDBA 自动诊断报告生成逻辑

## 概述

SmartDBA 使用 **Inspection Service（智能巡检服务）** 来自动触发和生成数据库诊断报告。系统支持三种触发方式：定时巡检、手动触发和异常触发。

## 核心组件

### 1. InspectionConfig（巡检配置）
**位置**: `backend/models/inspection_config.py`

每个数据源（datasource）都有一个巡检配置，包含：

```python
class InspectionConfig:
    datasource_id: int              # 关联的数据源ID
    enabled: bool                   # 是否启用巡检（默认True）
    
    # 调度配置
    schedule_interval: int          # 巡检间隔（秒），默认86400（每天）
    last_scheduled_at: datetime     # 上次执行时间
    next_scheduled_at: datetime     # 下次执行时间
    
    # AI分析配置
    use_ai_analysis: bool           # 是否使用AI分析（默认True）
    ai_model_id: int                # 使用的AI模型ID
    kb_ids: List[int]               # 关联的知识库ID列表
    
    # 阈值规则
    threshold_rules: dict           # 阈值配置
    # 示例：
    # {
    #   "cpu_usage": {"threshold": 80, "duration": 60},
    #   "disk_usage": {"threshold": 80, "duration": 300},
    #   "memory_usage": {"threshold": 85, "duration": 60},
    #   "connections": {"threshold": 100, "duration": 120}
    # }
```

**默认配置**：
- 巡检间隔：86400秒（24小时）
- CPU使用率阈值：80%，持续60秒
- 磁盘使用率阈值：80%，持续300秒
- 内存使用率阈值：85%，持续60秒
- 连接数阈值：100，持续120秒

### 2. InspectionTrigger（巡检触发记录）
**位置**: `backend/models/inspection_trigger.py`

记录每次巡检触发的审计信息：

```python
class InspectionTrigger:
    datasource_id: int              # 数据源ID
    trigger_type: str               # 触发类型：'scheduled'/'manual'/'anomaly'
    trigger_reason: str             # 触发原因（如"CPU 95% > 80% for 60s"）
    metric_snapshot: dict           # 触发时的指标快照
    triggered_at: datetime          # 触发时间
    processed: bool                 # 是否已处理
    report_id: int                  # 生成的报告ID
```

### 3. InspectionService（巡检服务）
**位置**: `backend/services/inspection_service.py`

核心服务，负责调度和触发巡检。

## 触发流程

### 启动流程

```
应用启动 (backend/app.py)
    ↓
创建 InspectionService 实例
    ↓
调用 inspection_service.start()
    ↓
初始化所有数据源的巡检配置 (initialize_all_configs)
    ↓
启动后台调度循环 (_scheduler_loop)
```

**初始化逻辑** (`initialize_all_configs`):
1. 查询所有数据源
2. 为没有配置的数据源创建默认 InspectionConfig
3. 设置 next_scheduled_at = 当前时间 + 86400秒

### 定时巡检流程

```
_scheduler_loop (每60秒检查一次)
    ↓
查询 enabled=True 且 next_scheduled_at <= 当前时间 的配置
    ↓
对每个配置：
    ↓
    创建 InspectionTrigger (type='scheduled')
    ↓
    更新 last_scheduled_at = 当前时间
    ↓
    更新 next_scheduled_at = 当前时间 + schedule_interval
    ↓
    异步生成报告 (_generate_report_async)
```

**调度器代码**:
```python
async def _scheduler_loop(self):
    while self.running:
        async with self.db_session_factory() as db:
            now = datetime.utcnow()
            result = await db.execute(
                select(InspectionConfig).where(
                    and_(
                        InspectionConfig.enabled == True,
                        InspectionConfig.next_scheduled_at <= now
                    )
                )
            )
            configs = result.scalars().all()

            for config in configs:
                # 触发巡检
                await self.trigger_inspection(
                    db, config.datasource_id, "scheduled", "Scheduled inspection"
                )
                # 更新下次执行时间
                config.last_scheduled_at = now
                config.next_scheduled_at = now + timedelta(seconds=config.schedule_interval)

            await db.commit()

        await asyncio.sleep(60)  # 每60秒检查一次
```

### 手动触发流程

```
用户点击"立即巡检"按钮
    ↓
前端调用 POST /api/inspections/trigger
    ↓
InspectionService.trigger_inspection(type='manual')
    ↓
创建 InspectionTrigger
    ↓
同步生成报告 (_generate_report)
    ↓
返回报告ID给前端
```

### 异常触发流程（当前未实现）

**设计思路**（未来可实现）:
```
MetricCollector 采集指标
    ↓
检查是否超过阈值规则
    ↓
如果超过阈值且持续时间满足条件：
    ↓
    InspectionService.trigger_inspection(type='anomaly')
    ↓
    创建 InspectionTrigger (reason="CPU 95% > 80% for 60s")
    ↓
    异步生成报告
```

**注意**: 当前代码中 `metric_collector.py` 设置了 `_inspection_service` 引用，但未实现阈值检查逻辑。

## 报告生成流程

```
InspectionService._generate_report(trigger_id)
    ↓
查询 InspectionTrigger
    ↓
调用 ReportGenerator.generate_inspection_report(trigger_id)
    ↓
创建 Report 记录 (status='generating')
    ↓
调用 generate_report_with_skills() 使用AI生成报告
    ↓
AI执行诊断skills收集数据
    ↓
AI分析数据并生成Markdown报告
    ↓
更新 Report (status='completed', content_md=报告内容)
    ↓
更新 InspectionTrigger (processed=True, report_id=报告ID)
```

**报告生成器代码** (`ReportGenerator.generate_inspection_report`):
```python
async def generate_inspection_report(self, trigger_id: int) -> int:
    # 查询触发记录和配置
    trigger = await self.db.execute(select(InspectionTrigger)...)
    datasource = await self.db.execute(select(Datasource)...)
    config = await self.db.execute(select(InspectionConfig)...)

    # 创建报告记录
    report = Report(
        datasource_id=trigger.datasource_id,
        title=f"{trigger.trigger_type.capitalize()} Inspection - {datasource.name}",
        report_type="inspection",
        status="generating",
        trigger_type=trigger.trigger_type,
        trigger_id=trigger.id,
        trigger_reason=trigger.trigger_reason,
        generation_method="ai"
    )
    self.db.add(report)
    await self.db.flush()

    # 使用AI生成报告
    content_md, skill_executions = await generate_report_with_skills(
        datasource_id=datasource.id,
        datasource_name=datasource.name,
        datasource_type=datasource.db_type,
        trigger_reason=trigger.trigger_reason or "Inspection requested",
        system_prompt=INSPECTION_REPORT_PROMPT,
        db=self.db,
        model_id=config.ai_model_id if config else None,
        timeout_seconds=300
    )

    # 更新报告状态
    report.content_md = content_md
    report.skill_executions = skill_executions
    report.status = "completed"
    report.completed_at = datetime.utcnow()

    await self.db.commit()
    return report.id
```

## 时间线示例

假设数据源ID=1，配置为每天巡检：

```
2026-03-14 00:00:00  应用启动
                     ↓
                     创建 InspectionConfig
                     next_scheduled_at = 2026-03-15 00:00:00

2026-03-14 00:01:00  调度器开始运行（每60秒检查）
                     ↓
                     检查：next_scheduled_at > now，不触发

2026-03-15 00:01:00  调度器检查
                     ↓
                     检查：next_scheduled_at <= now，触发！
                     ↓
                     创建 InspectionTrigger (type='scheduled')
                     ↓
                     生成报告（异步）
                     ↓
                     更新 next_scheduled_at = 2026-03-16 00:01:00

2026-03-16 00:01:00  下一次定时巡检
```

## 配置管理

### 查看巡检配置
```http
GET /api/inspections/configs/{datasource_id}
```

### 更新巡检配置
```http
PUT /api/inspections/configs/{datasource_id}
{
  "enabled": true,
  "schedule_interval": 86400,
  "use_ai_analysis": true,
  "threshold_rules": {
    "cpu_usage": {"threshold": 80, "duration": 60}
  }
}
```

### 手动触发巡检
```http
POST /api/inspections/trigger
{
  "datasource_id": 1,
  "reason": "Manual inspection requested by admin"
}
```

### 查看巡检历史
```http
GET /api/inspections/triggers?datasource_id=1&limit=10
```

### 查看巡检报告
```http
GET /api/inspections/reports?datasource_id=1&limit=10
```

## 当前限制

1. **异常触发未实现**: 虽然有阈值配置，但 `metric_collector.py` 中未实现阈值检查逻辑
2. **阈值规则未生效**: `threshold_rules` 配置存在但未被使用
3. **单一调度间隔**: 所有数据源使用相同的检查频率（60秒），无法针对不同数据源设置不同的检查频率

## 未来改进方向

1. **实现异常触发**:
   - 在 `metric_collector.py` 中添加阈值检查
   - 当指标超过阈值且持续时间满足条件时，自动触发巡检

2. **灵活的调度策略**:
   - 支持 cron 表达式（如"每天凌晨2点"）
   - 支持不同数据源不同的巡检频率

3. **智能阈值**:
   - 基于历史数据自动学习正常范围
   - 动态调整阈值避免误报

4. **报告优化**:
   - 支持报告模板自定义
   - 支持报告邮件/钉钉/企业微信通知

## 相关文件

- `backend/services/inspection_service.py` - 巡检服务核心逻辑
- `backend/services/report_generator.py` - 报告生成器
- `backend/models/inspection_config.py` - 巡检配置模型
- `backend/models/inspection_trigger.py` - 巡检触发记录模型
- `backend/routers/inspections.py` - 巡检API路由
- `backend/app.py` - 服务启动和初始化
- `backend/services/metric_collector.py` - 指标采集（预留异常触发接口）
