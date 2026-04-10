# 网络探针防告警风暴实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每轮指标采集前执行网络探针检测，网络异常时跳过所有数据源采集并发一条汇总告警，防止告警风暴。

**Architecture:** 新增 `network_probe.py` 模块封装 ping 探测逻辑；在 `collect_all_metrics()` 头部调用探针，失败则创建全局告警并返回，成功则自动解除已有的网络告警后继续正常采集；通过 system_config 键 `network_probe_host` 使目标可配置，默认 `127.0.0.1`。

**Tech Stack:** Python asyncio、asyncio.create_subprocess_exec、SQLAlchemy async、APScheduler、FastAPI

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/services/network_probe.py` | 新建 | ping 探测逻辑，返回 bool |
| `backend/services/metric_collector.py` | 修改 | `collect_all_metrics()` 头部加探针；新增 `_handle_network_probe_failure()` 和 `_auto_resolve_network_probe_alerts()` |
| `backend/app.py` | 修改 | lifespan 中 seed `network_probe_host` 默认配置 |
| `test_network_probe.py` | 新建 | 探针逻辑单元测试 |

---

## Task 1: 新建 network_probe.py

**Files:**
- Create: `backend/services/network_probe.py`
- Test: `test_network_probe.py`

- [ ] **Step 1: 写失败测试**

新建 `test_network_probe.py`：

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_check_network_success():
    """ping 返回 0 时应返回 True"""
    from backend.services.network_probe import check_network

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await check_network("127.0.0.1")
    assert result is True


@pytest.mark.asyncio
async def test_check_network_failure():
    """ping 返回非 0 时应返回 False"""
    from backend.services.network_probe import check_network

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock(return_value=1)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await check_network("192.0.2.1")
    assert result is False


@pytest.mark.asyncio
async def test_check_network_timeout():
    """超时应返回 False"""
    from backend.services.network_probe import check_network

    async def slow_wait():
        await asyncio.sleep(10)

    mock_proc = MagicMock()
    mock_proc.wait = slow_wait

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await check_network("192.0.2.1")
    assert result is False


@pytest.mark.asyncio
async def test_check_network_exception():
    """创建进程异常应返回 False"""
    from backend.services.network_probe import check_network

    with patch("asyncio.create_subprocess_exec", side_effect=OSError("no ping")):
        result = await check_network("127.0.0.1")
    assert result is False
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest test_network_probe.py -v
```

预期：`ModuleNotFoundError: No module named 'backend.services.network_probe'`

- [ ] **Step 3: 实现 network_probe.py**

新建 `backend/services/network_probe.py`：

```python
import asyncio
import logging
import platform

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 3.0  # 整体超时秒数


async def check_network(host: str) -> bool:
    """
    使用系统 ping 命令检测网络连通性。

    Returns:
        True 表示可达，False 表示不可达或超时或异常
    """
    try:
        # macOS/Linux: ping -c 1 -W 2 <host>
        # Windows: ping -n 1 -w 2000 <host>
        if platform.system().lower() == "windows":
            args = ["ping", "-n", "1", "-w", "2000", host]
        else:
            args = ["ping", "-c", "1", "-W", "2", host]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=_PROBE_TIMEOUT)
        return proc.returncode == 0

    except asyncio.TimeoutError:
        logger.warning(f"Network probe timeout for host: {host}")
        try:
            proc.kill()
        except Exception:
            pass
        return False
    except Exception as e:
        logger.warning(f"Network probe error for host {host}: {e}")
        return False
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest test_network_probe.py -v
```

预期：4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/services/network_probe.py test_network_probe.py
git commit -m "feat: add network probe module with ping-based connectivity check"
```

---

## Task 2: 在 metric_collector.py 中集成探针

**Files:**
- Modify: `backend/services/metric_collector.py`（`collect_all_metrics` 函数及新增两个辅助函数）

- [ ] **Step 1: 在 `collect_all_metrics()` 之前添加两个辅助函数**

在 `metric_collector.py` 的 `collect_all_metrics` 函数定义之前（约第 476 行附近），插入以下两个函数：

```python
async def _handle_network_probe_failure(host: str):
    """创建全局网络探针失败告警（若尚无活跃告警）"""
    try:
        from backend.services.alert_service import AlertService
        async with async_session() as db:
            # 检查是否已存在活跃的网络告警，避免重复
            from sqlalchemy import select, and_
            from backend.models.alert_message import AlertMessage
            result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.metric_name == "network_probe",
                        AlertMessage.status.in_(["active", "acknowledged"])
                    )
                )
            )
            if result.scalars().first():
                logger.debug("Network probe alert already active, skipping creation")
                return

            await AlertService.create_alert(
                db=db,
                datasource_id=0,
                alert_type="system_error",
                severity="critical",
                metric_name="network_probe",
                trigger_reason=f"网络探针失败：无法连通 {host}"
            )
            logger.warning(f"Created network probe failure alert (host={host})")
    except Exception as e:
        logger.error(f"Error creating network probe alert: {e}", exc_info=True)


async def _auto_resolve_network_probe_alerts():
    """探针恢复后自动解除所有活跃的网络告警"""
    try:
        from backend.services.alert_service import AlertService
        from sqlalchemy import select, and_
        from backend.models.alert_message import AlertMessage
        async with async_session() as db:
            result = await db.execute(
                select(AlertMessage).where(
                    and_(
                        AlertMessage.metric_name == "network_probe",
                        AlertMessage.status.in_(["active", "acknowledged"])
                    )
                )
            )
            alerts = result.scalars().all()
            for alert in alerts:
                await AlertService.resolve_alert(db, alert.id)
                logger.info(f"Auto-resolved network probe alert {alert.id}: network restored")
    except Exception as e:
        logger.error(f"Error auto-resolving network probe alerts: {e}", exc_info=True)
```

- [ ] **Step 2: 修改 `collect_all_metrics()` 函数**

将现有的 `collect_all_metrics()` 函数替换为：

```python
async def collect_all_metrics():
    """Collect metrics for all active datasources."""
    try:
        # 网络探针：采集前先检测网络连通性
        from backend.services.network_probe import check_network
        from backend.services.config_service import get_config as _get_config

        async with async_session() as _probe_db:
            probe_host = await _get_config(_probe_db, "network_probe_host", default="127.0.0.1")

        network_ok = await check_network(probe_host)
        if not network_ok:
            logger.warning(f"Network probe failed (host={probe_host}), skipping all datasource collection")
            await _handle_network_probe_failure(probe_host)
            return

        # 网络正常，自动解除已有的网络告警
        await _auto_resolve_network_probe_alerts()

        async with async_session() as db:
            result = await db.execute(
                select(Datasource.id).where(Datasource.is_active == True)
            )
            datasource_ids = [row[0] for row in result.fetchall()]

        tasks = [collect_metrics_for_connection(ds_id) for ds_id in datasource_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error in collect_all_metrics: {e}")
```

- [ ] **Step 3: 启动服务验证无报错**

```bash
python run.py
```

观察启动日志，确认 `Metric collector started` 正常输出，无 ImportError。Ctrl+C 停止。

- [ ] **Step 4: 提交**

```bash
git add backend/services/metric_collector.py
git commit -m "feat: integrate network probe into collect_all_metrics to prevent alert storms"
```

---

## Task 3: 在 app.py 中 seed 默认配置

**Files:**
- Modify: `backend/app.py`（lifespan 函数中 seed 默认配置的部分）

- [ ] **Step 1: 在 Aliyun defaults 的 seed 循环之后添加网络探针配置**

找到 `backend/app.py` 约第 97 行 `logger.info("Default system configs seeded")` 之前，在 Aliyun seed 循环结束后插入：

```python
        # Seed network probe config
        _probe_exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == "network_probe_host"))
        if not _probe_exists.scalar_one_or_none():
            await _config_service.set_config(
                _db,
                key="network_probe_host",
                value="127.0.0.1",
                value_type="string",
                description="网络探针目标地址，采集前用于检测网络连通性（默认 127.0.0.1，可改为网关 IP）",
                category="monitoring"
            )
```

- [ ] **Step 2: 启动服务，确认配置已写入**

```bash
python run.py &
sleep 3
# 查询系统配置（或在前端系统配置页搜索 network_probe_host）
python -c "
import asyncio
from backend.database import async_session
from backend.services.config_service import get_config
async def check():
    async with async_session() as db:
        v = await get_config(db, 'network_probe_host')
        print('network_probe_host =', v)
asyncio.run(check())
"
```

预期输出：`network_probe_host = 127.0.0.1`

Ctrl+C 停止服务。

- [ ] **Step 3: 提交**

```bash
git add backend/app.py
git commit -m "feat: seed network_probe_host default config on startup"
```

---

## Task 4: 手动验证全流程

- [ ] **Step 1: 启动服务**

```bash
python run.py
```

- [ ] **Step 2: 模拟探针失败**

临时将 `network_probe_host` 改为一个不可达 IP（如 `192.0.2.99`）：

```bash
python -c "
import asyncio
from backend.database import async_session
from backend.services.config_service import set_config
async def update():
    async with async_session() as db:
        await set_config(db, key='network_probe_host', value='192.0.2.99', value_type='string')
asyncio.run(update())
"
```

等待一个采集周期（默认 60 秒），观察日志：
- 应出现 `Network probe failed ... skipping all datasource collection`
- 数据库中应有一条 `metric_name=network_probe` 的 active 告警
- 不应产生各个数据源的 connection_failure 告警

- [ ] **Step 3: 恢复探针目标**

```bash
python -c "
import asyncio
from backend.database import async_session
from backend.services.config_service import set_config
async def update():
    async with async_session() as db:
        await set_config(db, key='network_probe_host', value='127.0.0.1',
                      value_type='string')
asyncio.run(update())
"
```

等待一个采集周期，确认：
- 日志出现 `Auto-resolved network probe alert`
- 数据源采集恢复正常

- [ ] **Step 4: 最终提交**

```bash
git add docs/superpowers/plans/2026-03-21-network-probe-alert-storm.md
git commit -m "docs: add network probe implementation plan"
```