# 进程详情功能

## 功能概述

在主机详情页面的"实时进程"标签中，用户可以点击任意进程行查看该进程的详细信息，包括：

- 基本信息（PID、用户、状态、CPU/内存使用率等）
- 完整命令行参数
- 磁盘 I/O 统计（读写字节数、系统调用次数）
- 网络连接信息
- 环境变量（前20个）
- 工作目录

## 技术实现

### 后端

#### 1. 新增 API 接口

**路径**: `GET /api/host/{host_id}/processes/{pid}`

**功能**: 获取指定主机上指定进程的详细信息

**实现位置**: `backend/routers/host.py`

#### 2. 进程服务扩展

**文件**: `backend/services/host_process_service.py`

**新增方法**:
- `get_process_detail(ssh_client, pid)`: 通过 SSH 获取进程详细信息
- `_parse_process_detail(pid, raw_data)`: 解析原始数据为结构化信息

**数据采集**:
- 使用 `ps` 命令获取进程基本信息
- 读取 `/proc/{pid}/cmdline` 获取完整命令行
- 读取 `/proc/{pid}/io` 获取 I/O 统计
- 使用 `lsof` 或 `netstat` 获取网络连接
- 读取 `/proc/{pid}/environ` 获取环境变量
- 使用 `readlink /proc/{pid}/cwd` 获取工作目录

### 前端

#### 1. API 客户端

**文件**: `frontend/js/api.js`

**新增方法**:
```javascript
getProcessDetail(hostId, pid) { 
    return this.get(`/api/host/${hostId}/processes/${pid}`); 
}
```

#### 2. 页面组件

**文件**: `frontend/js/pages/host-detail.js`

**新增功能**:
- 进程表格行添加点击事件
- 模态框显示进程详情
- 实时数据格式化（字节数、百分比等）

**新增方法**:
- `_showProcessDetail(pid)`: 显示进程详情模态框
- 更新 `_renderProcessTable()`: 添加点击事件绑定

#### 3. 样式

**文件**: `frontend/css/host-detail.css`

**新增样式**:
- `.process-detail-container`: 详情容器
- `.process-detail-section`: 信息分组
- `.process-detail-grid`: 网格布局
- `.process-detail-code`: 代码块样式
- `.process-row:hover`: 行悬停效果

## 使用方法

1. 进入主机详情页面
2. 切换到"实时进程"标签
3. 点击任意进程行
4. 查看进程详细信息模态框
5. 点击关闭按钮或模态框外部区域关闭

## 数据说明

### 磁盘 I/O 指标

- **读取字节数**: 从存储设备实际读取的字节数
- **写入字节数**: 向存储设备实际写入的字节数
- **读取字符数**: 进程读取的总字符数（包括缓存）
- **写入字符数**: 进程写入的总字符数（包括缓存）
- **读取系统调用**: read() 系统调用次数
- **写入系统调用**: write() 系统调用次数

### 网络连接

显示进程当前的所有网络连接，包括：
- 监听端口
- 已建立的连接
- 本地地址和远程地址

### 环境变量

出于性能和安全考虑，只显示前20个环境变量。

## 测试

运行测试脚本：

```bash
python tests/test_process_detail.py
```

测试覆盖：
- 进程详情数据采集
- 数据解析和格式化
- 各字段正确性验证

## 注意事项

1. **权限要求**:
   - 磁盘 I/O 数据需要 root 权限读取 `/proc/{pid}/io`
   - 建议配置 SSH 用户的 sudo 免密权限：`sudo visudo` 添加 `username ALL=(ALL) NOPASSWD: /bin/cat /proc/*/io`
   - 如果没有 sudo 权限，磁盘 I/O 数据将显示为 0

2. **网络连接采集**:
   - 优先使用 `ss` 命令（需要 sudo 权限显示进程信息）
   - 回退到 `netstat` 命令
   - 最后尝试 `lsof` 命令（如果已安装）
   - 如果都不可用，网络连接部分将为空

3. **系统兼容性**:
   - 进程详情采集依赖 `/proc` 文件系统（仅 Linux）
   - 某些容器环境可能限制 `/proc` 访问
   - 进程可能在查询期间结束，需要处理异常情况

4. **性能考虑**:
   - 环境变量只显示前 20 个，避免数据过大
   - 命令行参数会被截断显示
   - 建议不要频繁刷新进程详情

## 配置 sudo 免密权限

为了让普通用户能够读取进程 I/O 数据，建议配置 sudo 免密权限：

```bash
# 编辑 sudoers 文件
sudo visudo

# 添加以下行（替换 username 为实际用户名）
username ALL=(ALL) NOPASSWD: /bin/cat /proc/*/io
username ALL=(ALL) NOPASSWD: /usr/bin/ss
username ALL=(ALL) NOPASSWD: /bin/netstat

# 或者允许所有命令免密（不推荐生产环境）
username ALL=(ALL) NOPASSWD: ALL
```

测试配置：
```bash
# 测试是否可以免密执行
sudo -n cat /proc/1/io
sudo -n ss -tnp
```

## 未来改进

- [ ] 添加进程树视图
- [ ] 支持实时刷新进程详情
- [ ] 添加进程操作（终止、暂停、恢复）
- [ ] 支持进程性能历史趋势图
- [ ] 添加进程资源限制信息（cgroup、ulimit）
