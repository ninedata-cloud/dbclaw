# 阿里云 RDS CPU/内存指标刷新后消失 - 快速修复指南

## 问题现象

在阿里云 RDS 实例的性能监控界面：
- 刚打开时可以看到 CPU 和内存使用率数据
- 定时刷新后，CPU 和内存使用率显示为 `- -`（无数据）

## 修复步骤

### 1. 确认修改已应用

修改的文件：
- `backend/services/integration_scheduler.py`

修改内容：
- 将集成采集的指标合并到 `db_status` 类型的快照中
- 使用扁平的数据格式，与前端兼容

### 2. 重启服务

```bash
# 停止当前运行的服务
pkill -f "python run.py"

# 或者在运行服务的终端按 Ctrl+C

# 重新启动服务
python run.py
```

### 3. 验证修复

**方法 1：运行测试脚本**
```bash
python test_integration_merge.py
```

等待 1-2 分钟后再次运行，确认输出中显示：
```
✓ 最新的 db_status 快照包含 CPU/内存指标，修改生效！
```

**方法 2：前端验证**
1. 打开性能监控页面
2. 选择阿里云 RDS 数据源
3. 等待定时刷新（约 60 秒）或手动点击刷新按钮
4. 确认 CPU 和内存使用率持续显示，不会变成 `- -`

### 4. 检查日志

如果问题仍然存在，检查日志：

```bash
# 查看最近的日志
tail -f logs/app.log

# 或者在运行服务的终端查看输出
```

关键日志信息：
- `成功写入 X 个数据源的指标（共 Y 个指标）` - 表示指标已合并
- `集成 阿里云 RDS 监控数据采集 执行成功` - 表示集成运行成功

## 常见问题

### Q1: 重启后仍然没有 CPU/内存数据

**可能原因**：
1. 数据源未配置 `external_instance_id`
   - 解决：在数据源配置中设置 `external_instance_id` 为阿里云 RDS 实例 ID（如 `rm-bp1xxx`）

2. 阿里云 AccessKey 未配置
   - 解决：在系统配置中设置 `aliyun_access_key_id` 和 `aliyun_access_key_secret`

3. 阿里云 API 调用失败
   - 解决：检查日志中的错误信息，确认网络连接和 API 权限

### Q2: 旧的 integration_metric 快照如何处理

旧的 `integration_metric` 快照不会影响功能，但会占用存储空间。

**清理方法**（可选）：
```sql
-- 删除旧的 integration_metric 快照
DELETE FROM metric_snapshots
WHERE metric_type = 'integration_metric';
```

### Q3: 如何确认集成正在运行

```bash
# 运行测试脚本
python test_integration_merge.py
```

查看输出中的"[步骤 4] 检查集成配置"部分，确认：
- 找到启用的监控集成
- 最后运行时间是最近的时间（1-2 分钟内）

## 技术细节

### 修改前的数据流

```
阿里云 API → 集成系统 → metric_snapshots (integration_metric)
                                ↓
                            前端查询不到（只查 db_status）
```

### 修改后的数据流

```
阿里云 API → 集成系统 → 合并到最新的 db_status 快照
                                ↓
                            前端正常显示
```

### 数据格式对比

**修改前（integration_metric）**：
```json
{
  "metric_name": "cpu_usage",
  "value": 45.2,
  "labels": {"source": "aliyun_rds"},
  "unit": "%"
}
```

**修改后（db_status）**：
```json
{
  "cpu_usage": 45.2,
  "memory_usage": 78.5,
  "qps": 6.42,
  "tps": 0.0,
  ...
}
```

## 相关文档

- 详细修复说明：`docs/fixes/2026-03-19-aliyun-rds-cpu-memory-refresh-fix.md`
- 测试脚本：`test_integration_merge.py`

## 修复日期

2026-03-19
