# OS 系统指标监控实现总结

## 实现内容

### 1. OS 指标采集服务 (os_metrics_collector.py)

**功能：**
- 通过 SSH 连接到数据库服务器
- 采集 Linux 和 Windows 系统指标
- 支持密码和密钥两种认证方式

**采集的 Linux 指标：**

#### 核心指标
- `cpu_usage` - CPU 使用率 (%)
- `memory_usage` - 内存使用率 (%)
- `disk_usage` - 磁盘使用率 (%)

#### 磁盘 IO
- `disk_reads_per_sec` - 每秒磁盘读取次数
- `disk_writes_per_sec` - 每秒磁盘写入次数

#### 网络 IO
- `network_rx_bytes` - 接收字节数（累积）
- `network_tx_bytes` - 发送字节数（累积）

#### 系统负载
- `load_avg_1min` - 1分钟负载平均值
- `load_avg_5min` - 5分钟负载平均值
- `load_avg_15min` - 15分钟负载平均值

#### 系统信息
- `cpu_cores` - CPU 核心数
- `total_memory_mb` - 总内存 (MB)
- `boot_time` - 系统启动时间

**采集方法：**
```python
# Linux
- CPU: top 命令或 mpstat
- 内存: free 命令
- 磁盘: df 命令
- 磁盘IO: iostat 命令
- 网络: /proc/net/dev
- 负载: /proc/loadavg
```

### 2. 集成到指标采集器 (metric_collector.py)

**工作流程：**
```
1. 采集数据库指标
   ↓
2. 标准化数据库指标
   ↓
3. 如果配置了 SSH，采集 OS 指标
   ↓
4. 合并数据库指标 + OS 指标
   ↓
5. 保存到 metric_snapshots
   ↓
6. 异常检测
```

**新增函数：**
- `_collect_os_metrics(db, ssh_host_id)` - 通过 SSH 采集 OS 指标

### 3. 更新基线学习器 (baseline_learner.py)

**新增学习的指标：**
- `load_avg_1min`, `load_avg_5min`, `load_avg_15min`
- `disk_reads_per_sec`, `disk_writes_per_sec`

**基线计算：**
- 使用 3-sigma 规则计算动态阈值
- 需要至少 100 个样本
- 自动过滤异常值（IQR 方法）

### 4. 更新异常检测器 (metric_collector.py)

**检测策略：**

**CRITICAL/IMPORTANT 级别：**
- 数据库指标：connections, qps, tps
- OS 指标：cpu_usage, memory_usage, disk_usage
- 系统负载：load_avg_1min, load_avg_5min
- 磁盘 IO：disk_reads_per_sec, disk_writes_per_sec

**NORMAL 级别：**
- 数据库指标：connections, qps, tps
- 关键 OS 指标：cpu_usage, memory_usage

## 配置要求

### 1. 数据源需要关联 SSH 主机

在数据源配置中设置 `ssh_host_id`：

```sql
UPDATE datasources
SET ssh_host_id = 1
WHERE id = 4;
```

### 2. SSH 主机配置

确保 SSH 主机表中有正确的配置：

```sql
SELECT * FROM ssh_hosts;
```

需要的字段：
- `host` - SSH 服务器地址
- `port` - SSH 端口（默认 22）
- `username` - SSH 用户名
- `auth_type` - 认证类型（password 或 key）
- `password_encrypted` - 加密的密码（如果使用密码认证）
- `private_key_encrypted` - 加密的私钥（如果使用密钥认证）

### 3. 服务器端要求

**Linux 服务器需要安装的工具：**
```bash
# 基础工具（通常已安装）
top, free, df

# 可选工具（用于更详细的指标）
iostat  # 磁盘 IO 统计
mpstat  # CPU 统计
```

安装方法：
```bash
# CentOS/RHEL
yum install sysstat

# Ubuntu/Debian
apt-get install sysstat
```

## 使用示例

### 1. 配置数据源关联 SSH

```python
# 通过 API 或直接修改数据库
datasource.ssh_host_id = 1
```

### 2. 重启服务

```bash
# 重启后端服务以加载新代码
```

### 3. 等待指标采集

系统会自动：
- 每 15 秒采集一次指标（包括 OS 指标）
- 每小时学习一次基线
- 实时检测异常

### 4. 查看采集的 OS 指标

```python
import sqlite3
import json

conn = sqlite3.connect('data/smartdba.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT data FROM metric_snapshots
    WHERE datasource_id = 4
    ORDER BY collected_at DESC
    LIMIT 1
''')

data = json.loads(cursor.fetchone()[0])
print('OS 指标:')
print(f'  CPU: {data.get("cpu_usage")}%')
print(f'  Memory: {data.get("memory_usage")}%')
print(f'  Disk: {data.get("disk_usage")}%')
print(f'  Load Avg (1min): {data.get("load_avg_1min")}')
print(f'  Disk Reads/s: {data.get("disk_reads_per_sec")}')
print(f'  Disk Writes/s: {data.get("disk_writes_per_sec")}')

conn.close()
```

### 5. 查看 OS 指标基线

```python
cursor.execute('''
    SELECT metric_name, mean, upper_threshold, confidence_score
    FROM metric_baselines
    WHERE datasource_id = 4
    AND metric_name IN ('cpu_usage', 'memory_usage', 'disk_usage', 'load_avg_1min')
''')

print('OS 指标基线:')
for row in cursor.fetchall():
    print(f'  {row[0]}: mean={row[1]:.2f}, threshold={row[2]:.2f}, confidence={row[3]:.2f}')
```

### 6. 查看 OS 相关异常

```python
cursor.execute('''
    SELECT detected_at, anomaly_type, severity,
           affected_metrics, current_value, baseline_value, deviation_percent
    FROM anomalies
    WHERE datasource_id = 4
    AND affected_metrics LIKE '%cpu_usage%'
       OR affected_metrics LIKE '%memory_usage%'
       OR affected_metrics LIKE '%load_avg%'
    ORDER BY detected_at DESC
    LIMIT 10
''')

print('OS 相关异常:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[2]} - current={row[4]:.2f}, baseline={row[5]:.2f}, deviation={row[6]:.1f}%')
```

## 监控指标说明

### CPU 使用率 (cpu_usage)
- **正常范围**：0-80%
- **警告阈值**：> 80%
- **严重阈值**：> 95%
- **异常场景**：CPU 密集型查询、索引缺失、死锁

### 内存使用率 (memory_usage)
- **正常范围**：0-85%
- **警告阈值**：> 85%
- **严重阈值**：> 95%
- **异常场景**：内存泄漏、缓存过大、连接数过多

### 磁盘使用率 (disk_usage)
- **正常范围**：0-80%
- **警告阈值**：> 80%
- **严重阈值**：> 90%
- **异常场景**：日志膨胀、数据增长、临时文件未清理

### 系统负载 (load_avg_1min)
- **正常范围**：< CPU 核心数
- **警告阈值**：> CPU 核心数 * 1.5
- **严重阈值**：> CPU 核心数 * 2
- **异常场景**：高并发、IO 等待、进程阻塞

### 磁盘 IO (disk_reads/writes_per_sec)
- **正常范围**：取决于硬件和负载
- **异常场景**：全表扫描、索引缺失、大量写入

## 故障排查

### 问题 1：OS 指标采集失败

**症状：**
```json
{
  "connections": 42,
  "qps": 1234,
  "tps": 567
  // 没有 cpu_usage, memory_usage 等
}
```

**原因：**
1. 数据源未配置 `ssh_host_id`
2. SSH 连接失败（密码错误、网络问题）
3. SSH 主机配置不正确

**解决：**
```sql
-- 检查数据源配置
SELECT id, name, ssh_host_id FROM datasources WHERE id = 4;

-- 检查 SSH 主机配置
SELECT * FROM ssh_hosts WHERE id = 1;

-- 测试 SSH 连接
ssh username@host -p port
```

### 问题 2：某些 OS 指标为空

**症状：**
```json
{
  "cpu_usage": 45.2,
  "memory_usage": 67.8,
  "disk_usage": null,  // 为空
  "load_avg_1min": null
}
```

**原因：**
1. 服务器缺少必要的工具（iostat, mpstat）
2. 命令执行权限不足
3. 命令输出格式不匹配

**解决：**
```bash
# 安装 sysstat 工具包
yum install sysstat  # CentOS/RHEL
apt-get install sysstat  # Ubuntu/Debian

# 检查命令是否可用
which iostat
which mpstat

# 测试命令输出
top -bn1 | grep 'Cpu(s)'
free | grep Mem
df -h /
```

### 问题 3：SSH 连接超时

**症状：**
日志中出现 "Failed to collect OS metrics via SSH: timeout"

**原因：**
1. 网络延迟高
2. SSH 服务器响应慢
3. 防火墙阻止

**解决：**
```python
# 增加超时时间（在 os_metrics_collector.py 中）
ssh_client.connect(..., timeout=30)  # 从 10 秒增加到 30 秒
```

## 性能影响

### SSH 连接开销
- 每次采集需要建立 SSH 连接：~100-500ms
- 执行命令：~50-200ms
- 总开销：~150-700ms

### 优化建议
1. **连接复用**：保持 SSH 连接，避免每次重连
2. **批量执行**：一次 SSH 会话执行多个命令
3. **异步采集**：OS 指标和数据库指标并行采集

## 下一步优化

1. **SSH 连接池**：复用 SSH 连接，减少连接开销
2. **Agent 模式**：在服务器上部署轻量级 agent，通过 HTTP 采集
3. **更多指标**：进程列表、网络连接、文件句柄
4. **智能采集**：根据重要性动态调整采集频率
5. **历史趋势**：OS 指标的长期趋势分析
