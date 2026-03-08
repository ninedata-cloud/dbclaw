# AI Guardian System 工作原理与问题分析

## 系统架构

AI Guardian System 由三个核心组件组成：

### 1. Baseline Learner（基线学习器）
- **功能**：自动学习数据库的健康基线
- **学习周期**：每小时运行一次
- **学习数据**：分析过去 30 天的历史指标数据
- **基线计算**：使用 3-sigma 规则计算动态阈值
- **最小样本数**：需要至少 100 个样本才能建立基线

### 2. Importance Classifier（重要性分级器）
- **功能**：自动评估数据库的重要性
- **分级**：CRITICAL（关键）、IMPORTANT（重要）、NORMAL（普通）
- **评分因子**：
  - 连接频率
  - 查询量
  - 业务时间活跃度
  - 数据变化率
  - 下游依赖数
  - 历史事件数
  - 用户交互次数

### 3. Anomaly Detector（异常检测器）
- **功能**：基于基线检测异常
- **检测策略**：
  - CRITICAL 级别：实时检测（每次指标采集都检测）
  - IMPORTANT 级别：实时检测
  - NORMAL 级别：批量检测（频率较低）
- **检测指标**：cpu_usage, memory_usage, disk_usage, connections

## 当前问题

### 问题 1：指标字段不匹配

**PostgreSQL 采集的字段：**
```json
{
  "connections_active": 42,
  "connections_total": 60,
  "connections_idle": 6,
  "xact_commit": 6174976,
  "cache_hit_rate": 96.53,
  "tup_returned": 8734030895,
  ...
}
```

**系统期望的字段：**
- `cpu_usage` - CPU 使用率（%）
- `memory_usage` - 内存使用率（%）
- `disk_usage` - 磁盘使用率（%）
- `connections` - 连接数
- `qps` - 每秒查询数
- `tps` - 每秒事务数

**结果：**
- 基线学习器找不到期望的字段，无法建立基线（0 个基线）
- 异常检测器找不到指标值（都是 None），无法检测异常

### 问题 2：重要性评分过低

数据源 `101.37.209.117-pg` 的评分：
- **分数**：25.0（满分 100）
- **级别**：NORMAL
- **检测模式**：batch（批量）
- **采集间隔**：60 秒

由于是 NORMAL 级别，不会进行实时异常检测，即使有高负载也不会触发告警。

### 问题 3：缺少系统级指标

PostgreSQL connector 只采集数据库内部指标，不采集：
- CPU 使用率（需要从操作系统获取）
- 内存使用率（需要从操作系统获取）
- 磁盘使用率（需要从操作系统获取）

## 解决方案

### 方案 1：标准化指标字段（推荐）

为每个数据库类型创建指标映射，将数据库特定字段映射到标准字段：

**PostgreSQL 映射：**
- `connections` ← `connections_active`
- `qps` ← 计算 `tup_returned` 的增量
- `tps` ← 计算 `xact_commit` 的增量

**添加系统指标采集：**
- 通过 SSH 连接到数据库服务器
- 采集 CPU、内存、磁盘使用率
- 或使用 pg_stat_statements 扩展

### 方案 2：扩展基线学习器

让基线学习器支持数据库特定的指标：
- PostgreSQL：connections_active, cache_hit_rate, xact_commit
- MySQL：threads_connected, qps, tps
- 每种数据库有自己的异常检测规则

### 方案 3：手动提升重要性

通过 API 手动设置数据源为 CRITICAL 级别：
```bash
POST /api/guardian/importance/4/recalculate
```

或直接修改数据库：
```sql
UPDATE datasource_importance
SET importance_score = 90,
    importance_tier = 'CRITICAL',
    anomaly_detection_mode = 'realtime',
    collection_interval = 15
WHERE datasource_id = 4;
```

## 当前状态总结

**数据源 4 (101.37.209.117-pg)：**
- ✅ 指标采集正常（1297 个快照）
- ✅ 重要性已评估（NORMAL 级别）
- ❌ 没有基线（字段不匹配）
- ❌ 没有异常检测（级别太低 + 没有基线）
- ❌ 缺少系统级指标（CPU、内存、磁盘）

**为什么 TPCC 压测没有触发异常：**
1. 数据源被评为 NORMAL 级别，不进行实时检测
2. 没有建立基线，无法判断什么是异常
3. 采集的指标字段与检测器期望的不匹配
4. 缺少 CPU、内存等系统级指标

## 建议

1. **短期**：实现指标字段映射，让现有指标能被检测
2. **中期**：添加系统级指标采集（通过 SSH 或 agent）
3. **长期**：为每种数据库类型定制异常检测规则
