# 网络探针防告警风暴设计文档

**日期**：2026-03-21
**状态**：已批准

## 问题描述

当 DbGuard 所在服务器网络断开时，所有数据库连接采集均失败，`collect_all_metrics()` 为每个数据源各自触发连接失败告警和 AI 诊断任务，造成告警风暴。

## 解决方案：全局网络探针

在每轮指标采集开始前，先执行一次网络连通性探测。探测失败则跳过本轮所有数据源采集，只发一条全局网络异常告警；探测成功则正常采集，并自动解除已有的网络告警。

## 架构设计

### 流程

```
collect_all_metrics()
  ├─ 读取 system_config: network_probe_host（默认 127.0.0.1）
  ├─ 执行 ping 探测
  │   ├─ 失败 → 创建/保持一条 network_probe 告警，跳过所有数据源采集，返回
  │   └─ 成功 → 自动解除 network_probe 告警（若存在），继续正常采集
  └─ 并发采集所有数据源指标（现有逻辑不变）
```

### 新增文件：`backend/services/network_probe.py`

- `async def check_network(host: str) -> bool`
  - 调用系统 `ping -c 1 -W 2 <host>` 命令
  - 使用 `asyncio.create_subprocess_exec` 异步执行
  - 整体超时 3 秒（`asyncio.wait_for`），超时视为失败
  - 返回值：`True` 表示可达，`False` 表示不可达或异常

### 系统配置新增键

| 键名 | 默认值 | 说明 |
|------|--------|------|
| `network_probe_host` | `127.0.0.1` | 网络探针目标主机，可由管理员在系统配置页修改 |

默认值 `127.0.0.1` 的含义：探测本机回环地址，确认本机网络栈正常（若需探测外部网关，管理员手动修改为网关 IP）。

### 告警设计

- `alert_type`：`system_error`
- `metric_name`：`network_probe`
- `datasource_id`：`0`（全局告警，不属于任何单一数据源；AlertMessage.datasource_id 列为 `nullable=False`，故以 `0` 作为全局系统告警的约定标识）
- `severity`：`critical`
- `trigger_reason`：`"网络探针失败：无法连通 {host}"`

**防重复**：创建告警前查询是否已有 `active`/`acknowledged` 状态的 `network_probe` 告警，有则跳过创建。
**自动恢复**：探针成功时，自动 resolve 所有 active 的 `network_probe` 告警。

## 改动范围

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/services/network_probe.py` | 新增 | ping 探测逻辑 |
| `backend/services/metric_collector.py` | 修改 | `collect_all_metrics()` 头部加探针调用 |
| `backend/app.py` 或 default_configs 相关位置 | 修改 | 写入默认 `network_probe_host = 127.0.0.1` |

前端无需改动，现有系统配置页已支持通用键值对的读写。

## 边界情况

- **探针目标本身是数据库主机**：不建议，应使用网关或独立节点，避免目标宕机误判为网络故障（管理员责任）
- **127.0.0.1 默认值**：仅确认本机网络栈，不能判断外网可达性；适合大多数内网部署场景
- **采集跳过但不清除违规状态**：`ThresholdChecker` 内存中的 violation_start_times 不会因网络断开而被错误地清除，恢复后可正常继续计时
- **datasource_id = 0**：AlertMessage.datasource_id 列为 `nullable=False`，全局网络告警使用 `0` 作为约定标识，不对应任何真实数据源

## 不在范围内

- 多探针目标（仅单一目标）
- 前端展示网络探针状态
- 探针失败时对已存在的 threshold_violation 告警的处理（保持不变，不自动解除）
