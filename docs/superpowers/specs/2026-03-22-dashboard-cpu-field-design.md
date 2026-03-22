# Dashboard CPU 字段统一设计

## 背景

首页资源大盘中，数据源 `polardb-x测试无锁-polardb` 未显示 CPU 信息。排查发现首页卡片仅读取 `cpu_usage` 或 `os_cpu_usage`，而 OS 指标采集链路中存在 `cpu_usage_percent` 字段，导致首页资源大盘在部分数据源上拿不到 CPU 值并显示 `--`。

## 目标

统一 CPU 指标字段命名为 `cpu_usage`，消除 `cpu_usage_percent`、`os_cpu_usage` 等并行命名在首页资源大盘链路中的使用。

本次仅处理首页资源大盘所依赖的采集与展示链路，不扩展到其他无关指标字段。

## 设计原则

1. 只保留一个 CPU 字段名：`cpu_usage`
2. 优先在后端统一字段，避免前端继续做字段兼容
3. 不做额外重构，不引入与本问题无关的改动

## 根因分析

### 前端读取逻辑

首页资源大盘在渲染 CPU 时读取如下字段：

- `cpu_usage`
- `os_cpu_usage`

如果两者都不存在，则显示 `--`。

### 后端采集逻辑

OS 指标采集服务返回的是 `cpu_usage_percent`，而不是 `cpu_usage`。这导致同一条数据链路中的 CPU 字段命名不一致。

### 结论

问题根因是：**后端 CPU 指标字段命名与首页资源大盘读取字段不一致**。

## 方案

### 变更点 1：统一 OS 指标采集输出字段

在 `backend/services/os_metrics_service.py` 中，将 CPU 输出字段从 `cpu_usage_percent` 改为 `cpu_usage`。

#### 目的

确保 OS 指标在最上游就使用统一字段名，减少后续链路中的转换和分支判断。

### 变更点 2：保持指标合并后的字段一致性

在 `backend/services/metric_collector.py` 中，确认 OS 指标合并进 `normalized_status` 后，最终写入 `MetricSnapshot.data` 的 CPU 字段为 `cpu_usage`。

#### 目的

保证首页批量接口返回的最新指标数据中，CPU 字段稳定存在于 `metric.data.cpu_usage`。

### 变更点 3：首页资源大盘只读取 `cpu_usage`

在 `frontend/js/pages/dashboard.js` 中，首页 CPU 展示逻辑仅使用 `metricData.cpu_usage`，不再读取 `os_cpu_usage`。

#### 目的

消除前端兼容分支，让字段约定单一明确。

## 数据流

统一后的数据流如下：

1. OS 指标采集生成 `cpu_usage`
2. 指标采集器将 `cpu_usage` 合并进 `db_status.data`
3. 批量大盘接口返回 `metric.data.cpu_usage`
4. 首页资源大盘读取 `cpu_usage` 并显示百分比

## 影响范围

### 直接影响

- `backend/services/os_metrics_service.py`
- `backend/services/metric_collector.py`
- `frontend/js/pages/dashboard.js`

### 预期影响

- 首页资源大盘 CPU 显示恢复正常
- CPU 字段约定更一致，后续维护成本降低

### 非目标

本次不处理以下事项：

- 其他指标字段统一
- 监控详情页或其他页面的额外展示逻辑调整
- 历史数据回填或迁移

## 风险与约束

### 风险

如果项目其他位置仍然依赖 `cpu_usage_percent` 或 `os_cpu_usage`，统一后这些位置可能受到影响。

### 应对方式

修改前后应检查代码中对这些旧字段的引用，确认首页资源大盘链路之外没有必须保留的依赖，或至少明确其现状。

## 验证计划

完成修改后验证以下内容：

1. 首页资源大盘卡片读取字段为 `cpu_usage`
2. 批量接口 `/api/metrics/batch/dashboard` 返回的 `metric.data` 包含 `cpu_usage`
3. 数据源 `polardb-x测试无锁-polardb` 在首页显示 CPU 数值而非 `--`
4. 不引入明显的前端渲染报错或后端采集异常

## 实施边界

本次只做根因修复，不追加兼容字段，不做顺手优化。修复完成后，如需推广到其他页面，再单独评估。