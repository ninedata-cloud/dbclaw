# SSH Agent 认证快速上手指南

## 快速开始

如果你的服务器已经通过 SSH 打通了通道，可以通过以下步骤快速添加到 DBClaw：

### 1. 确认 SSH Agent 已配置

```bash
# 检查 SSH Agent 状态
ssh-add -l

# 如果看到密钥列表，说明已配置好
# 如果提示 "Could not open a connection to your authentication agent"，需要启动 Agent：
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa
```

### 2. 在 DBClaw 中添加主机

1. 打开 DBClaw 界面，进入"主机管理"页面
2. 点击"New Host"按钮
3. 填写表单：
   - **名称**：服务器名称（如"生产数据库服务器"）
   - **主机**：服务器 IP 或域名
   - **端口**：22（默认）
   - **用户名**：SSH 登录用户名
   - **Auth Type**：选择 **"SSH Agent"**
4. 点击保存

### 3. 测试连接

点击主机列表中的"测试连接"按钮（插头图标），验证连接是否成功。

## 为什么选择 SSH Agent？

| 对比项 | SSH Agent | 密码认证 | 私钥认证 |
|-------|-----------|---------|---------|
| 安全性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 便捷性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| 凭据存储 | 不存储 | 加密存储 | 加密存储 |
| 适用场景 | 开发/运维环境 | 简单环境 | 生产环境 |

**SSH Agent 的优势**：
- ✅ 无需在 DBClaw 中存储任何凭据
- ✅ 使用系统已有的 SSH 密钥
- ✅ 支持密码保护的私钥（密码只需输入一次）
- ✅ 可以随时撤销访问（从 Agent 中移除密钥）

## 常见问题

### Q: SSH Agent 认证失败怎么办？

**A:** 按以下步骤排查：

1. **检查 SSH Agent 是否运行**
   ```bash
   ssh-add -l
   ```
   如果提示错误，运行：
   ```bash
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_rsa
   ```

2. **验证能否直接 SSH 连接**
   ```bash
   ssh username@target-host
   ```
   如果不能直接连接，DBClaw 也无法连接。

3. **检查目标主机的公钥配置**
   ```bash
   # 复制公钥到目标主机
   ssh-copy-id username@target-host
   ```

### Q: 重启后 SSH Agent 失效怎么办？

**A:** SSH Agent 是会话级的，重启后需要重新启动：

```bash
# 方法 1：每次手动启动
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa

# 方法 2：添加到 shell 配置文件（推荐）
# 在 ~/.bashrc 或 ~/.zshrc 中添加：
if [ -z "$SSH_AUTH_SOCK" ]; then
    eval "$(ssh-agent -s)"
    ssh-add ~/.ssh/id_rsa 2>/dev/null
fi
```

### Q: 可以同时使用多个密钥吗？

**A:** 可以！SSH Agent 支持加载多个密钥：

```bash
ssh-add ~/.ssh/id_rsa
ssh-add ~/.ssh/id_ed25519
ssh-add ~/.ssh/company_key

# 查看已加载的密钥
ssh-add -l
```

### Q: 如何提高安全性？

**A:** 建议：

1. **使用密码保护的私钥**
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   # 设置密码时不要留空
   ```

2. **设置 Agent 超时**
   ```bash
   # 密钥 1 小时后自动从 Agent 中移除
   ssh-add -t 3600 ~/.ssh/id_rsa
   ```

3. **使用 Ed25519 密钥**（比 RSA 更安全）
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

## 技术细节

### 工作流程

```
DBClaw → paramiko → SSH Agent → 私钥 → 目标主机
```

1. DBClaw 通过 paramiko 发起 SSH 连接
2. paramiko 设置 `allow_agent=True`
3. paramiko 自动查找系统的 SSH Agent
4. SSH Agent 使用已加载的私钥进行认证
5. 私钥始终保留在本地，不会传输

### 支持的密钥类型

- RSA (2048/4096 bit)
- Ed25519（推荐）
- ECDSA
- DSA（不推荐，已过时）

## 下一步

配置完成后，你可以：

1. 在"数据源管理"中添加数据库，选择通过此主机的 SSH 隧道连接
2. 在"AI 诊断"中使用需要 OS 级别访问的诊断技能
3. 在"监控"中查看主机的 CPU、内存、磁盘使用情况

## 相关文档

- [完整技术文档](./SSH_AGENT_AUTH.md)
- [主机管理指南](./HOST_MANAGEMENT.md)
- [SSH 隧道配置](./SSH_TUNNEL.md)
