# AI Guardian System 修复总结

## 修复内容

### 1. 创建指标标准化服务 (metric_normalizer.py)

**功能：**
- 将不同数据库的指标映射到统一格式
- 支持 PostgreSQL, MySQL, SQL Server, Oracle
- 自动计算 QPS/TPS（基于累积值的增量）

**标准化字段：**
- `connections` - 活跃连接数
- `qps` - 每秒查询数
- `tps` - 每秒事务数
- `cpu_usage` - CPU使用率（待实现）
- `memory_usage` - 内存使用率（待实现）
- `disk_usage` - 磁盘使用率（待实现）

**PostgreSQL 映射：**
```
connections ← connections_active
qps ← tup_returned 的增量速率
tps ← xact_commit 的增量速率
```

### 2. 更新指标采集器 (metric_collector.py)

**改进：**
- 采集后自动标准化指标
- 降低异常检测门槛：NORMAL 级别也会检测 connections/qps/tps
- 增强错误处理

**检测策略：**
- CRITICAL/IMPORTANT: 检测所有指标（cpu, memory, disk, connections, qps, tps）
- NORMAL: 检测数据库指标（connections, qps, tps）

### 3. 更新基线学习器 (baseline_learner.py)

**改进：**
- 支持标准化后的字段名
- 支持数据库特定指标（如 cache_hit_rate, connections_active）

## 工作原理

### 指标采集流程

```
1. 数据库连接器采集原始指标
   ↓
2. MetricNormalizer 标准化指标
   ↓
3. 保存到 metric_snapshots 表
   ↓
4. 推送到 WebSocket 订阅者
   ↓
5. 异常检测器检查指标
```

### 基线学习流程

```
1. 每小时运行一次
   ↓
2. 从 metric_snapshots 读取过去 30 天数据
   ↓
3. 提取标准化指标（connections, qps, tps 等）
   ↓
4. 计算统计基线（mean, stddev, p50, p95, p99）
   ↓
5. 使用 3-sigma 规则计算动态阈值
   ↓
6. 保存到 metric_baselines 表
```

### 异常检测流程

```
1. 每次指标采集后触发
   ↓
2. 获取数据源重要性级别
   ↓
3. 根据级别选择检测指标
   ↓
4. 对每个指标：
   - 查询基线
   - 比较当前值与阈值
   - 如果超出阈值，创建异常记录
   ↓
5. 保存到 anomalies 表
```

## 测试步骤

### 1. 重启后端服务

```bash
# 停止当前服务
# 重新启动
python -m uvicorn backend.app:app --reload
```

### 2. 等待指标采集

等待 1-2 分钟，让系统采集几轮标准化后的指标。

### 3. 检查标准化指标

```bash
python -c "
import sqlite3
import json
conn = sqlite3.connect('data/smartdba.db')
cursor = conn.cursor()

cursor.execute('SELECT data FROM metric_snapshots WHERE datasource_id = 4 ORDER BY collected_at DESC LIMIT 1')
data = json.loads(cursor.fetchone()[0])
print('标准化后的指标:')
print(f'  connections: {data.get(\"connections\")}')
print(f'  qps: {data.get(\"qps\")}')
print(f'  tps: {data.get(\"tps\")}')
print(f'  connections_active: {data.get(\"connections_active\")}')
print(f'  cache_hit_rate: {data.get(\"cache_hit_rate\")}')
conn.close()
"
```

### 4. 手动触发基线学习

```bash
curl -X POST http://localhost:8000/api/guardian/baselines/4/recalculate
```

### 5. 检查基线

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/smartdba.db')
cursor = conn.cursor()

cursor.execute('SELECT metric_name, mean, upper_threshold, confidence_score, sample_count FROM metric_baselines WHERE datasource_id = 4')
print('基线数据:')
for row in cursor.fetchall():
    print(f'  {row[0]}: mean={row[1]:.2f}, threshold={row[2]:.2f}, confidence={row[3]:.2f}, samples={row[4]}')
conn.close()
"
```

### 6. 模拟高负载（可选）

如果 TPCC 压测还在运行，系统应该能检测到：
- connections 激增
- qps/tps 激增

### 7. 检查异常记录

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/smartdba.db')
cursor = conn.cursor()

cursor.execute('SELECT detected_at, anomaly_type, severity, current_value, baseline_value, deviation_percent FROM anomalies WHERE datasource_id = 4 ORDER BY detected_at DESC LIMIT 10')
print('检测到的异常:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]} - {row[2]} (current={row[3]:.2f}, baseline={row[4]:.2f}, deviation={row[5]:.1f}%)')
conn.close()
"
```

### 8. 查看 AI Guardian 界面

访问 http://localhost:8000 → AI Guardian System
- 应该能看到基线数据
- 应该能看到异常记录（如果有）

## 已知限制

### 1. 缺少系统级指标

当前不采集：
- CPU 使用率
- 内存使用率
- 磁盘使用率

**解决方案：**
- 方案 A: 通过 SSH 连接到数据库服务器采集
- 方案 B: 部署轻量级 agent
- 方案 C: 使用数据库扩展（如 pg_stat_statements）

### 2. QPS/TPS 计算延迟

第一次采集时无法计算 QPS/TPS（需要两次采集才能计算增量）。

### 3. 基线需要时间建立

- 需要至少 100 个样本
- 建议运行 1-2 天后基线才稳定

## 下一步优化

1. **添加系统级指标采集**
2. **优化重要性评分算法**（考虑实际负载）
3. **实现主动诊断**（Phase 3）
4. **添加告警通知**（邮件、Slack、钉钉）
5. **支持自定义阈值**
