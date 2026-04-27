# MySQL 连接数显示为 0 的问题修复

## 问题描述

MySQL 实例的活跃连接数和总连接数显示为 `0/0/1120`，这是不合理的。

## 根本原因

在 `backend/services/mysql_service.py` 的 `get_status()` 方法中，连接数采集存在以下问题：

1. **类型转换不安全**：`SHOW GLOBAL STATUS` 返回的 `Threads_connected` 和 `Threads_running` 可能是字符串类型（如 `"0"` 或 `"25"`），直接使用 `int(status.get("Threads_running", 0))` 可能导致转换失败
2. **优先级错误**：原代码使用 `max()` 取两个数据源的最大值，但当 `SHOW GLOBAL STATUS` 返回字符串 `"0"` 时，`int("0")` 结果为 0，导致错误地使用了 `information_schema.PROCESSLIST` 的值
3. **权限问题**：如果用户没有 `PROCESS` 权限，`information_schema.PROCESSLIST` 只能看到自己的连接，导致 `visible_threads_connected` 很小

## 修复方案

### 1. 添加安全类型转换函数

```python
def safe_int(value, default=0):
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
```

### 2. 调整优先级逻辑

```python
# 优先使用 SHOW GLOBAL STATUS 的值（更准确且不受权限限制）
global_threads_running = safe_int(status.get("Threads_running"))
global_threads_connected = safe_int(status.get("Threads_connected"))

# 只在 GLOBAL STATUS 无效时才使用 PROCESSLIST（可能受权限限制）
visible_threads_running = safe_int(process_stats[1]) if process_stats else 0
visible_threads_connected = safe_int(process_stats[0]) if process_stats else 0

# 优先使用全局状态值，只在为 0 时才考虑可见连接数
threads_running = global_threads_running if global_threads_running > 0 else visible_threads_running
threads_connected = global_threads_connected if global_threads_connected > 0 else visible_threads_connected
```

### 3. 添加调试日志

当连接数为 0 时，记录详细的采集信息：

```python
if threads_connected == 0 or threads_running == 0:
    logger.warning(
        f"MySQL connection metrics may be incorrect - "
        f"global: connected={global_threads_connected}, running={global_threads_running}; "
        f"visible: connected={visible_threads_connected}, running={visible_threads_running}; "
        f"final: connected={threads_connected}, running={threads_running}"
    )
```

## 测试验证

修复后的逻辑：

- **正常情况**：`SHOW GLOBAL STATUS` 返回 `Threads_connected=25`，最终显示 25
- **字符串 "0"**：`SHOW GLOBAL STATUS` 返回 `"0"`，回退到 `PROCESSLIST` 的值
- **缺少键**：`SHOW GLOBAL STATUS` 不包含 `Threads_*`，回退到 `PROCESSLIST` 的值
- **PROCESSLIST 失败**：使用 `SHOW GLOBAL STATUS` 的值
- **两者都为 0**：显示 0 并记录告警日志

## 如何验证修复

1. 重启服务：`python run.py`
2. 查看实例详情页面的连接数显示
3. 如果仍显示 0，检查日志中的告警信息：
   ```bash
   grep "MySQL connection metrics may be incorrect" logs/app.log
   ```
4. 日志会显示两个数据源的原始值，帮助定位问题

## 相关文件

- `backend/services/mysql_service.py` - 主要修复文件
- `tests/test_mysql_connection_metrics.py` - 单元测试（需要完善 mock 设置）
