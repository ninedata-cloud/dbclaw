# 阿里云 RDS 监控界面 CPU/内存指标刷新后消失问题修复

## 问题描述

在阿里云 RDS 实例的性能监控界面，刚打开时可以看到 CPU 和内存使用率数据，但当界面定时刷新后，这些指标就显示为 `- -`（无数据）。

## 根本原因

1. **数据存储格式不一致**：
   - 前端监控页面只查询 `metric_type=db_status` 的指标
   - 阿里云 RDS 的 OS 指标（CPU、内存等）通过集成系统采集
   - 集成系统将指标存储为 `metric_type=integration_metric`，数据格式也不同

2. **数据格式差异**：
   - `db_status` 格式（扁平）：
     ```json
     {
       "cpu_usage": 45.2,
       "memory_usage": 78.5,
       "connections_active": 10,
       ...
     }
     ```
   - `integration_metric` 格式（嵌套）：
     ```json
     {
       "metric_name": "cpu_usage",
       "value": 45.2,
       "labels": {...},
       "unit": "%"
     }
     ```

3. **为什么初始加载时有数据**：
   - 可能显示的是之前通过 SSH 采集的 OS 指标（如果配置了 host_id）
   - 或者是缓存的旧数据

4. **为什么刷新后没有数据**：
   - 新的数据来自集成系统，但因为 `metric_type` 不同，前端查询不到

## 解决方案

修改集成调度器 (`backend/services/integration_scheduler.py`)，将阿里云 RDS 的指标合并到 `db_status` 类型的快照中。

### 修改内容

1. **按数据源分组指标**：
   ```python
   # 按 datasource_id 分组指标
   metrics_by_ds = {}
   for metric in metrics:
       ds_id = metric['datasource_id']
       if ds_id not in metrics_by_ds:
           metrics_by_ds[ds_id] = {}
       # 将指标添加到该数据源的字典中（扁平格式）
       metrics_by_ds[ds_id][metric['metric_name']] = metric['metric_value']
   ```

2. **查询最新的 db_status 快照**：
   ```python
   result = await session.execute(
       select(MetricSnapshot)
       .where(
           and_(
               MetricSnapshot.datasource_id == ds_id,
               MetricSnapshot.metric_type == "db_status"
           )
       )
       .order_by(desc(MetricSnapshot.collected_at))
       .limit(1)
   )
   latest_snapshot = result.scalar_one_or_none()
   ```

3. **合并指标数据**：
   ```python
   if latest_snapshot and latest_snapshot.data:
       # 如果有最新快照，合并数据
       merged_data = dict(latest_snapshot.data)
       merged_data.update(metric_data)
   else:
       # 如果没有最新快照，直接使用集成指标
       merged_data = metric_data
   ```

4. **创建新的 db_status 快照**：
   ```python
   snapshot = MetricSnapshot(
       datasource_id=ds_id,
       metric_type="db_status",  # 使用 db_status 类型，与前端兼容
       data=merged_data,
       collected_at=current_time
   )
   ```

### 修改的文件

- `backend/services/integration_scheduler.py`
  - 添加 `desc` 导入
  - 修改 `execute_integration` 函数中的指标写入逻辑

## 测试方法

1. **运行测试脚本**：
   ```bash
   python test_integration_merge.py
   ```

2. **检查输出**：
   - 确认找到使用集成采集的数据源
   - 确认最新的 db_status 快照包含 CPU/内存指标
   - 确认没有旧格式的 integration_metric 快照（或者有但不影响）

3. **前端验证**：
   - 打开性能监控页面
   - 等待定时刷新（或手动点击刷新按钮）
   - 确认 CPU 和内存使用率持续显示，不会变成 `- -`

## 影响范围

- **正面影响**：
  - 阿里云 RDS 的 OS 指标可以正常显示
  - 前端监控页面数据完整性提升
  - 统一了指标存储格式

- **潜在影响**：
  - 如果有其他代码依赖 `integration_metric` 类型的快照，需要相应调整
  - 数据库中会同时存在 `db_status` 和旧的 `integration_metric` 快照（不影响功能）

## 后续优化建议

1. **清理旧数据**：
   - 可以编写迁移脚本，清理旧的 `integration_metric` 快照
   - 或者设置定期清理任务

2. **统一指标采集**：
   - 考虑将所有监控指标统一使用 `db_status` 类型
   - 简化前端查询逻辑

3. **增强错误处理**：
   - 在集成执行失败时，记录详细的错误信息
   - 在前端显示采集状态和错误提示

## 相关文件

- `backend/services/integration_scheduler.py` - 集成调度器（已修改）
- `backend/utils/integration_templates.py` - 阿里云 RDS 集成模板
- `frontend/js/pages/monitor.js` - 前端监控页面
- `test_integration_merge.py` - 测试脚本

## 修复日期

2026-03-19
