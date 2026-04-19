# 主机配置功能说明

## 功能概述

在主机详情页面新增"主机配置"标签页，通过 SSH 连接主机并执行系统命令，实时获取并展示主机的详细系统配置信息。

## 功能特性

### 1. 系统信息
- 主机名
- 操作系统名称和版本
- 内核版本
- 系统运行时间
- 负载均衡（1分钟/5分钟/15分钟）

### 2. CPU 信息
- 处理器型号
- 物理 CPU 数量
- 逻辑核心数
- CPU 频率

### 3. 内存信息
- 总内存容量
- 已用内存（含使用率）
- 可用内存
- 缓冲区大小
- 缓存大小
- 交换分区使用情况

### 4. 磁盘信息
- 文件系统类型
- 挂载点
- 总容量、已使用、可用空间
- 使用率（带可视化进度条）

### 5. 网络接口
- 接口名称
- 地址类型（inet/inet6）
- IP 地址

## 技术实现

### 后端 API

**端点**: `GET /api/host-detail/{host_id}/config`

**响应结构**:
```json
{
  "cpu": {
    "model": "Intel(R) Xeon(R) CPU",
    "cores": 8,
    "physical_cpus": 2,
    "mhz": "2400.000"
  },
  "memory": {
    "MemTotal": "16384000 kB",
    "MemFree": "8192000 kB",
    "MemAvailable": "10240000 kB",
    ...
  },
  "disk": [
    {
      "filesystem": "/dev/sda1",
      "size": "100G",
      "used": "50G",
      "available": "50G",
      "use_percent": "50%",
      "mounted_on": "/"
    }
  ],
  "network": [
    {
      "interface": "eth0",
      "family": "inet",
      "address": "192.168.1.100/24"
    }
  ],
  "system": {
    "kernel": "5.10.0-21-amd64",
    "os_name": "Debian GNU/Linux",
    "os_version": "11 (bullseye)",
    "hostname": "db-server-01",
    "uptime_seconds": 864000,
    "load_avg_1": "0.50",
    "load_avg_5": "0.45",
    "load_avg_15": "0.40"
  },
  "collected_at": "2026-04-19T12:00:00Z"
}
```

### 前端实现

**文件**: `frontend/js/pages/host-detail.js`

**新增方法**:
- `_renderConfigTab(container)`: 渲染主机配置标签页

**API 调用**: `API.getHostConfig(hostId)`

### 样式文件

**文件**: `frontend/css/host-detail.css`

**新增样式类**:
- `.host-config-page`: 配置页面容器
- `.host-config-card`: 配置信息卡片
- `.host-config-table`: 配置信息表格
- `.host-config-progress`: 磁盘使用率进度条

## 使用方式

1. 进入主机详情页面：`/#host-detail?host={host_id}`
2. 点击"主机配置"标签页
3. 系统自动通过 SSH 获取主机配置信息
4. 点击"刷新配置"按钮可重新获取最新配置

## 安全说明

- 所有命令通过 SSH 连接池执行，复用已建立的连接
- 仅执行只读系统命令，不会修改主机配置
- 命令执行超时时间为 10 秒
- 执行失败不会影响其他功能

## 执行的系统命令

```bash
# CPU 信息
cat /proc/cpuinfo | grep 'model name' | head -1
nproc
cat /proc/cpuinfo | grep 'physical id' | sort -u | wc -l
cat /proc/cpuinfo | grep 'cpu MHz' | head -1

# 内存信息
cat /proc/meminfo | grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree):'

# 磁盘信息
df -h | grep -v tmpfs | grep -v devtmpfs

# 网络接口
ip -o addr show

# 系统信息
uname -r
cat /etc/os-release
hostname
cat /proc/uptime
cat /proc/loadavg
```

## 兼容性

- 支持主流 Linux 发行版（Debian、Ubuntu、CentOS、RHEL 等）
- 需要主机已配置 SSH 连接
- 需要 SSH 用户具有读取 `/proc` 和 `/etc` 的权限

## 未来优化方向

1. 添加更多硬件信息（GPU、RAID 等）
2. 支持配置信息导出（JSON/CSV）
3. 添加配置变更历史记录
4. 支持配置信息对比功能
5. 添加配置异常检测和告警
