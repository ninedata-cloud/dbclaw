# Dashboard CPU 字段统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一首页资源大盘 CPU 指标字段为 `cpu_usage`，让配置了主机的数据库数据源在首页卡片稳定显示 CPU 数值。

**Architecture:** 保持现有采集链路不变，只修复字段命名不一致的问题。后端 OS 指标采集统一输出 `cpu_usage`，指标采集器继续将其合并到 `db_status.data`，前端大盘只从 `metric.data.cpu_usage` 读取 CPU 值。

**Tech Stack:** FastAPI、SQLAlchemy async、原生 JavaScript、现有 MetricSnapshot 采集链路

---

## File Structure

- Modify: `backend/services/os_metrics_service.py`
  - 责任：通过 SSH 采集主机 OS 指标；本次统一 CPU 输出字段名。
- Modify: `frontend/js/pages/dashboard.js`
  - 责任：首页资源大盘卡片刷新与指标展示；本次只读取 `cpu_usage`。
- Verify only: `backend/services/metric_collector.py`
  - 责任：合并数据库指标与 OS 指标并写入 `MetricSnapshot.data`；本次确认无需额外转换逻辑。
- Verify only: `backend/routers/metrics.py`（重点核对 `_extract_metric_value()`）
  - 责任：批量大盘接口返回最新指标，并包含 CPU 字段提取兼容逻辑；本次确认首页读取路径是否会经过这里的旧字段映射。

## Notes Before Implementation

- 本次严格按 spec 执行：**只统一首页资源大盘链路中的 CPU 字段为 `cpu_usage`**。
- 实施顺序必须先后端、再前端，避免出现“前端已只读 `cpu_usage`，但后端尚未产出 `cpu_usage`”的临时回归窗口。
- 已发现仓库其他位置仍引用 `cpu_usage_percent` 或 `os_cpu_usage`，例如：
  - `templates/report_template.html`
  - `backend/services/ai_report_generator.py`
  - `test_threshold_checker.py`
- 这些引用默认**不在本次修复范围内**，但必须先审计并确认它们不阻断首页资源大盘链路。
- 由于仓库没有统一测试框架，本次以“可执行的最小验证脚本 + 定向搜索 + 页面验证”为主。
- 未经用户明确要求，**本计划不包含 git commit 步骤**。

### Task 1: 审计旧字段依赖并锁定修改边界

**Files:**
- Verify: `backend/services/os_metrics_service.py`
- Verify: `frontend/js/pages/dashboard.js`
- Verify: `backend/services/metric_collector.py`
- Verify: `backend/routers/metrics.py`（核对 `_extract_metric_value()` 中 `cpu_usage_percent` 映射是否会影响首页链路）
- Verify: `templates/report_template.html`
- Verify: `backend/services/ai_report_generator.py`
- Verify: `test_threshold_checker.py`

- [ ] **Step 1: 搜索旧字段引用位置**

Run: `rg -n "cpu_usage_percent|os_cpu_usage" backend frontend templates test_*.py`

Expected: 能列出所有旧字段引用位置。

- [ ] **Step 2: 静态核对首页批量接口读取路径**

确认以下代码路径：
- `frontend/js/pages/dashboard.js` 通过 `entry.metric.data` 直接读取首页卡片指标
- `backend/routers/metrics.py` 的 `/batch/dashboard` 组装结果时，`metric.data` 直接来自 `snap.data`

Expected: 首页链路中的 CPU 展示依赖 `entry.metric.data.cpu_usage`，而不是 `_extract_metric_value()` 的兼容映射。

- [ ] **Step 3: 标记首页链路中的必改文件**

根据搜索与静态核对结果，把以下文件明确标为首页链路必改/必核对：
- `backend/services/os_metrics_service.py`
- `backend/services/metric_collector.py`
- `backend/routers/metrics.py`
- `frontend/js/pages/dashboard.js`

Expected: 其余引用仅记录为“超出本次范围，不阻断首页显示”的观察项。

- [ ] **Step 4: 记录边界结论**

在实施记录中写明：`templates/report_template.html`、`backend/services/ai_report_generator.py`、`test_threshold_checker.py` 继续保留旧字段引用，不作为本次修复范围，除非后续验证发现它们直接参与首页资源大盘链路。

Expected: 修改边界清晰，不扩大范围。

### Task 2: 添加最小可重复后端验证并证明当前字段不符合约定

**Files:**
- Create: `test_os_metrics_service_cpu_field.py`
- Verify: `backend/services/os_metrics_service.py`
- Verify: `backend/services/ssh_service.py`

- [ ] **Step 1: 写失败测试脚本**

创建 `test_os_metrics_service_cpu_field.py`，使用最小桩对象覆盖 `execute_multi()` 返回结构，断言 `OSMetricsService.collect()` 结果包含 `cpu_usage`：

```python
from backend.services.os_metrics_service import OSMetricsService


class FakeSSH:
    def execute_multi(self, commands, timeout=30):
        return {
            commands[0]: "37.2",
            commands[1]: "100 50 50 50",
            commands[2]: "100 50 50 50%",
            commands[3]: "0.1 0.2 0.3",
            commands[4]: "1 2",
            commands[5]: "3 4",
            commands[6]: "5",
        }


def test_os_metrics_service_outputs_cpu_usage():
    metrics = OSMetricsService(FakeSSH()).collect()
    assert metrics["cpu_usage"] == 37.2
    assert "cpu_usage_percent" not in metrics
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `python -m pytest test_os_metrics_service_cpu_field.py -v`

Expected: FAIL，原因是当前实现仍输出 `cpu_usage_percent` 而不是 `cpu_usage`。

- [ ] **Step 3: 搜索当前合并链路**

Run: `rg -n "cpu_usage_percent|cpu_usage|normalized_status.update\(os_metrics\)" backend/services/os_metrics_service.py backend/services/metric_collector.py`

Expected:
- `backend/services/os_metrics_service.py` 当前输出 `cpu_usage_percent`
- `backend/services/metric_collector.py` 通过 `normalized_status.update(os_metrics)` 直接合并 OS 指标

### Task 3: 先修改后端统一输出 `cpu_usage`

**Files:**
- Modify: `backend/services/os_metrics_service.py`（CPU 解析代码块）
- Verify: `backend/services/metric_collector.py`（OS 指标合并代码块）
- Verify: `backend/routers/metrics.py`（`/batch/dashboard` 结果组装代码块）

- [ ] **Step 1: 修改 OS 指标采集字段名**

将 `backend/services/os_metrics_service.py` 中 CPU 字段由：

```python
metrics["cpu_usage_percent"] = float(outputs[0].strip() or "0")
metrics["cpu_usage_percent"] = 0.0
```

改为：

```python
metrics["cpu_usage"] = float(outputs[0].strip() or "0")
metrics["cpu_usage"] = 0.0
```

- [ ] **Step 2: 重新运行最小测试**

Run: `python -m pytest test_os_metrics_service_cpu_field.py -v`

Expected: PASS，且输出中包含 `cpu_usage`。

- [ ] **Step 3: 验证合并链路无需额外代码**

Run: `rg -n "cpu_usage_percent|cpu_usage|normalized_status.update\(os_metrics\)" backend/services/os_metrics_service.py backend/services/metric_collector.py backend/routers/metrics.py`

Expected:
- `backend/services/os_metrics_service.py` 只输出 `cpu_usage`
- `backend/services/metric_collector.py` 继续直接合并 `os_metrics`
- `/batch/dashboard` 仍直接返回 `entry.metric.data`，无需新增转换逻辑

### Task 4: 再收紧前端只读取 `cpu_usage`

**Files:**
- Modify: `frontend/js/pages/dashboard.js`（首页卡片 metricData CPU 读取代码块）

- [ ] **Step 1: 修改首页 CPU 读取逻辑**

将 `frontend/js/pages/dashboard.js` 中：

```js
const cpuVal = metricData.cpu_usage != null ? metricData.cpu_usage : metricData.os_cpu_usage;
```

改为：

```js
const cpuVal = metricData.cpu_usage != null ? metricData.cpu_usage : null;
```

- [ ] **Step 2: 验证首页不再依赖旧字段**

Run: `rg -n "os_cpu_usage" frontend/js/pages/dashboard.js`

Expected: 无匹配。

### Task 5: 端到端验证首页资源大盘链路

**Files:**
- Verify: `backend/routers/metrics.py`（`/batch/dashboard` 结果组装代码块）
- Verify: `frontend/js/pages/dashboard.js`（首页 CPU 展示代码块）
- Verify runtime behavior in local app

- [ ] **Step 1: 启动应用或确保应用运行**

Run: `python run.py`

Expected: 应用正常启动，无新增语法错误或导入错误。

- [ ] **Step 2: 先做通用接口验证**

通过已登录浏览器或现有会话检查 `/api/metrics/batch/dashboard` 响应，确认**任一配置了 `host_id` 且成功采集 OS 指标的数据源**返回：

```json
{
  "metric": {
    "data": {
      "cpu_usage": 12.3
    }
  }
}
```

Expected: 能看到 `metric.data.cpu_usage`，且首页链路不再依赖 `os_cpu_usage`。

- [ ] **Step 3: 再验证目标数据源**

打开首页资源大盘，确认 `polardb-x测试无锁-polardb` 卡片的 CPU 区域不再显示 `--`，而是显示类似 `12.3%` 的数值，并且进度条宽度正常。

Expected: 目标数据源首页显示 CPU 数值。

- [ ] **Step 4: 做最终静态搜索验证**

分别运行：
- `rg -n "os_cpu_usage" frontend/js/pages/dashboard.js`
- `rg -n "cpu_usage_percent" backend/services/os_metrics_service.py`

Expected: 两条命令都无输出。

## Manual Test Checklist

- [ ] 首页资源大盘正常打开
- [ ] `polardb-x测试无锁-polardb` 卡片显示 CPU 百分比
- [ ] CPU 进度条与数值一致
- [ ] 页面无明显前端报错
- [ ] 后端日志无新增采集异常

## Rollback Strategy

如果修复后首页仍无 CPU：
1. 先检查目标数据源是否配置了 `host_id`（`metric_collector.py:133` 只有配置主机才会采集 OS 指标）
2. 再检查 `/api/metrics/batch/dashboard` 是否真的返回了 `metric.data.cpu_usage`
3. 若接口无该字段，回到采集链路继续排查，不要在前端追加新兼容字段

## Out of Scope

- 不统一 `memory_usage_percent` / `disk_usage_percent`
- 不修改告警、报告生成、AI 报告中的旧字段引用
- 不做历史数据迁移
