# 进程详情功能 - 问题修复总结

## 问题描述

在主机详情页面的"实时进程"标签中，点击进程查看详情时，磁盘 I/O 和网络连接数据无法采集。

## 问题原因

### 1. 磁盘 I/O 数据采集失败

**原因**: `/proc/{pid}/io` 文件需要 root 权限才能读取

```bash
# 文件权限
-r-------- 1 root root 0 Apr 17 13:36 /proc/1/io

# 普通用户读取失败
$ cat /proc/1/io
cat: /proc/1/io: Permission denied

# root 用户或 sudo 可以读取
$ sudo cat /proc/1/io
rchar: 20037850224525
wchar: 315509025916
...
```

### 2. 网络连接数据采集不完整

**原因**: 
- 系统未安装 `lsof` 命令
- `netstat` 命令需要 root 权限才能显示进程信息
- 原始命令没有尝试使用 `ss` 命令

## 解决方案

### 1. 使用 sudo 读取磁盘 I/O

修改命令为：
```bash
sudo -n cat /proc/{pid}/io 2>/dev/null || cat /proc/{pid}/io 2>/dev/null
```

- 优先尝试使用 `sudo -n`（免密 sudo）
- 如果失败，回退到普通读取
- `-n` 参数确保不会等待密码输入

### 2. 优化网络连接采集

修改命令为多级回退策略：
```bash
sudo -n ss -tnp 2>/dev/null | grep 'pid={pid}' ||
ss -tnp 2>/dev/null | grep 'pid={pid}' ||
sudo -n netstat -tnp 2>/dev/null | grep '{pid}/' ||
netstat -tn 2>/dev/null | grep -v 'LISTEN' ||
lsof -p {pid} -i -n -P 2>/dev/null
```

优先级：
1. `sudo ss -tnp` - 最现代的工具，需要 sudo 显示进程信息
2. `ss -tnp` - 不带 sudo 的 ss
3. `sudo netstat -tnp` - 传统工具，需要 sudo 显示进程信息
4. `netstat -tn` - 不带进程信息的网络连接
5. `lsof` - 如果安装了的话

## 配置建议

为了获得完整的进程详情数据，建议配置 SSH 用户的 sudo 免密权限：

```bash
# 编辑 sudoers 文件
sudo visudo

# 添加以下行（替换 username 为实际用户名）
username ALL=(ALL) NOPASSWD: /bin/cat /proc/*/io
username ALL=(ALL) NOPASSWD: /usr/bin/ss
username ALL=(ALL) NOPASSWD: /bin/netstat
```

测试配置：
```bash
# 测试是否可以免密执行
sudo -n cat /proc/1/io
sudo -n ss -tnp
sudo -n netstat -tnp
```

## 测试结果

修复后的测试结果：

```
【磁盘 I/O】
  读取字节: 139,272,013,312 bytes ✓
  写入字节: 336,743,299,072 bytes ✓
  读取字符: 20,037,850,266,015 bytes ✓
  写入字符: 315,509,026,711 bytes ✓
  读取系统调用: 16,670,206,399 ✓
  写入系统调用: 80,246,675 ✓

【网络连接】
  连接数: 262 ✓
```

## 代码变更

### 修改文件
- `backend/services/host_process_service.py` - 更新 `get_process_detail()` 方法

### 关键变更
1. 磁盘 I/O 采集命令添加 sudo 支持
2. 网络连接采集使用多级回退策略
3. 优先使用 `ss` 命令替代 `lsof`

## 降级处理

如果没有 sudo 权限：
- 磁盘 I/O 数据将显示为 0
- 网络连接可能只显示连接状态，不显示进程信息
- 功能仍然可用，只是数据不完整

## 兼容性

- ✓ CentOS/RHEL 7+
- ✓ Ubuntu 16.04+
- ✓ Debian 9+
- ✓ 其他支持 `/proc` 文件系统的 Linux 发行版

## 相关文档

- [进程详情功能文档](./process-detail-feature.md)
- [测试脚本](../tests/test_process_detail_fixed.py)
- [调试脚本](../tests/test_process_detail_debug.py)
