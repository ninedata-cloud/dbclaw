# 数据库启动时间字段修复总结

## 问题描述
部分数据库服务的 `get_status()` 方法没有返回启动时间相关字段，导致前端无法正确展示数据库运行时长。

## 修复内容

### 后端修改

已为以下数据库服务添加启动时间字段：

1. **PostgreSQL** (`backend/services/postgres_service.py`)
   - 添加查询：`SELECT pg_postmaster_start_time() as start_time`
   - 返回字段：`uptime` (秒), `boot_time` (ISO格式时间戳)

2. **Oracle** (`backend/services/oracle_service.py`)
   - 添加查询：`SELECT startup_time FROM v$instance`
   - 返回字段：`uptime` (秒), `boot_time` (ISO格式时间戳)

3. **SQL Server** (`backend/services/sqlserver_service.py`)
   - 添加查询：`SELECT sqlserver_start_time FROM sys.dm_os_sys_info`
   - 返回字段：`uptime` (秒), `boot_time` (ISO格式时间戳)

4. **DM (达梦)** (`backend/services/dm_service.py`)
   - 添加查询：`SELECT STARTUP_TIME FROM V$INSTANCE`
   - 返回字段：`uptime` (秒), `boot_time` (ISO格式时间戳)

5. **openGauss** (`backend/services/opengauss_service.py`)
   - 添加查询：`SELECT pg_postmaster_start_time() as start_time`
   - 返回字段：`uptime` (秒), `boot_time` (ISO格式时间戳)

### 已有启动时间字段的数据库

以下数据库服务已经正确返回启动时间字段，无需修改：

- **MySQL**: 返回 `uptime` (秒)
- **TiDB**: 返回 `uptime` (秒)
- **OceanBase**: 返回 `uptime` (秒)
- **MongoDB**: 返回 `uptime` (秒)
- **Redis**: 返回 `uptime_in_seconds` (秒)

## 前端处理逻辑

前端 (`frontend/js/pages/monitor.js`) 已经实现了智能的启动时间处理：

```javascript
// 优先级：uptime > uptime_in_seconds > 从boot_time计算
let uptime = data.uptime || data.uptime_in_seconds || 0;
if (!uptime && data.boot_time) {
    const bootTime = new Date(data.boot_time);
    const now = new Date();
    uptime = Math.floor((now - bootTime) / 1000);
}
```

前端格式化函数 (`frontend/js/utils/format.js`) 将秒数转换为可读格式：
- 大于1天：显示 "Xd Yh"
- 大于1小时：显示 "Xh Ym"
- 大于1分钟：显示 "Xm"
- 小于1分钟：显示 "Xs"

## 字段规范

所有数据库服务的 `get_status()` 方法应返回以下启动时间相关字段之一：

1. **推荐方式**：同时返回 `uptime` 和 `boot_time`
   - `uptime`: 整数，数据库运行秒数
   - `boot_time`: 字符串，ISO格式的启动时间戳

2. **备选方式**：仅返回 `uptime` 或 `uptime_in_seconds`
   - 适用于数据库本身提供运行时长但不提供启动时间的情况

## 测试验证

运行测试脚本验证所有数据库服务：

```bash
python test_uptime_fields.py
```

预期结果：所有数据库服务都应该返回 ✓ 标记。

## 注意事项

1. **时区处理**：所有 `boot_time` 都转换为 UTC 时区的 ISO 格式字符串
2. **计算精度**：uptime 计算结果为整数秒，避免浮点数精度问题
3. **错误处理**：如果无法获取启动时间，返回 `uptime=0` 和 `boot_time=None`
4. **兼容性**：前端代码向后兼容，支持只有 `uptime` 或只有 `boot_time` 的情况
