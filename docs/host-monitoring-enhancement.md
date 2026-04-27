# 主机监控增强功能

## 功能概述

为主机详情页面的性能监控界面增加了磁盘 IO 流量、磁盘 IOPS 和网络 IO 指标的采集与展示，并统一了与数据源实例详情页面一致的 UI 样式。

## 更新内容

### 1. 后端指标采集增强

**文件**: `backend/services/os_metrics_collector.py`

#### 磁盘 IO 指标
- **磁盘 IOPS**:
  - `disk_read_iops`: 每秒读操作数
  - `disk_write_iops`: 每秒写操作数
  
- **磁盘流量**:
  - `disk_read_kb_per_sec`: 每秒读取 KB 数
  - `disk_write_kb_per_sec`: 每秒写入 KB 数

采集方法：
- 优先使用 `iostat -dx 1 2` 命令获取详细的磁盘 IO 统计
- 备用方案：从 `/proc/diskstats` 读取原始数据并计算

#### 网络 IO 指标
- **累计流量**:
  - `network_rx_bytes_total`: 接收总字节数
  - `network_tx_bytes_total`: 发送总字节数

- **实时速率**:
  - `network_rx_bytes_per_sec`: 每秒接收字节数
  - `network_tx_bytes_per_sec`: 每秒发送字节数
  - `network_rx_kb_per_sec`: 每秒接收 KB 数
  - `network_tx_kb_per_sec`: 每秒发送 KB 数

采集方法：
- 从 `/proc/net/dev` 读取网络接口统计（排除 lo 回环接口）
- 采样两次（间隔 1 秒）计算速率

### 2. 前端展示增强

**文件**: `frontend/js/pages/host-detail.js`

#### UI 样式统一
参考数据源实例详情的性能监控页面（`MonitorPage`），统一了以下样式：

1. **工具栏样式**
   - 使用 `instance-embedded-toolbar` 样式
   - 标题使用 `instance-embedded-title`
   - 时间范围选择器使用 `filter-select`

2. **指标卡片**
   - 使用 `grid-4` 和 `metric-card` 样式
   - 4 列网格布局展示关键指标
   - 包含：CPU 使用率、内存使用、磁盘使用、运行时间

3. **图表布局**
   - 使用统一的 `chart-grid` 2 列网格布局
   - 使用 `chart-panel` 卡片样式
   - 图表容器使用 `chart-container`（高度 180px）
   - 分为两个区域：基础指标（4个图表）+ 磁盘与网络 I/O（3个图表）

#### 新增图表
共 7 个图表：

**基础指标区域**：
1. **CPU 使用率图表** - 单线图（蓝色 #2f81f7）
2. **内存使用率图表** - 单线图（绿色 #10b981）
3. **磁盘使用率图表** - 单线图（橙色 #f59e0b）
4. **负载平均图表** - 单线图（紫色 #8b5cf6）

**磁盘与网络 I/O 区域**：
5. **磁盘 IOPS 图表** - 双线图：读（蓝色）+ 写（橙色）
6. **磁盘 I/O 流量图表** - 双线图：读（蓝色）+ 写（橙色）
7. **网络 I/O 流量图表** - 双线图：接收（绿色）+ 发送（紫色）

#### 图表配置优化
- 使用与 MonitorPage 一致的 Chart.js 配置
- 统一的颜色方案和透明度
- 优化的图例显示（多线图显示图例，单线图隐藏）
- 统一的网格线和坐标轴样式
- 改进的 tooltip 交互体验
- 智能的时间标签格式化（当天显示时分秒，跨天显示日期时间）

### 3. CSS 样式更新

**文件**: `frontend/css/host-detail.css`

移除了旧的自定义样式（`.host-monitor-container`, `.host-monitor-chart` 等），改为复用全局样式：
- 使用 `chart-grid` 和 `chart-panel`（来自 `charts.css`）
- 使用 `metric-card` 和 `grid-4`（来自全局样式）
- 使用 `instance-embedded-toolbar`（来自实例详情样式）

新增样式：
- `.host-monitor-page` - 页面容器
- `.host-monitor-page .instance-embedded-toolbar` - 工具栏样式
- `.host-monitor-page h3` - 区域标题样式

### 4. API 路径修正

**文件**: `frontend/js/api.js`

统一主机详情相关 API 路径为 `/api/host-detail/*`：
- `getHostSummary()`
- `getHostMetrics()`
- `getHostProcesses()`
- `getHostConnections()`
- `getHostNetworkTopology()`
- `getHostConfig()`

## 数据存储

所有新增指标存储在 `host_metric` 表的 `data` 字段（JSON 类型）中，不影响现有表结构。

## 测试

创建了两个测试文件：

1. **`tests/test_host_metric_collection.py`**
   - 测试真实 SSH 连接的指标采集
   - 需要有可用的主机配置

2. **`tests/test_host_metric_parsing.py`**
   - 测试指标解析逻辑（使用模拟数据）
   - 验证所有新增指标的正确性
   - ✅ 所有测试通过（11/11）

## 使用方法

1. 启动应用后，主机采集器会自动每分钟采集一次指标
2. 进入主机详情页面，切换到"性能监控"标签
3. 选择时间范围（1小时、6小时、24小时、3天、7天）
4. 查看 7 个性能图表的实时数据

## 兼容性

- 支持 Linux 系统（需要 `iostat` 命令支持磁盘 IO 统计）
- 网络 IO 采集基于 `/proc/net/dev`，所有 Linux 系统均支持
- 如果 `iostat` 不可用，会自动降级到 `/proc/diskstats` 读取

## 注意事项

1. 网络 IO 速率计算需要两次采样（间隔 1 秒），会略微增加采集时间
2. 磁盘 IOPS 和流量数据是所有磁盘的聚合值
3. 网络流量统计排除了 lo（回环）接口
4. 图表数据最多显示 1000 个数据点
5. 图表高度统一为 180px，与实例详情保持一致

## UI 对比

### 更新前
- 自定义样式，与实例详情不一致
- 6 个图表，缺少负载平均
- 图表高度 300px，较高
- 简单的工具栏布局

### 更新后
- 统一样式，与实例详情完全一致
- 7 个图表，新增负载平均
- 图表高度 180px，更紧凑
- 专业的工具栏和指标卡片布局
- 分区域展示（基础指标 + I/O 指标）

## 后续优化建议

1. 支持按磁盘分别展示 IO 指标
2. 支持按网络接口分别展示流量
3. 添加告警阈值配置（磁盘 IO 过高、网络流量异常等）
4. 支持导出性能数据为 CSV
5. 添加实时监控模式（WebSocket 推送）
