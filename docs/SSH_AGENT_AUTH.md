# SSH Agent 认证支持

## 功能说明

SmartDBA 现在支持使用 SSH Agent 进行主机认证，无需在界面上配置私钥或密码。这对于已经通过 SSH 打通服务器通道的场景特别有用。

## 认证方式对比

| 认证方式 | 适用场景 | 优点 | 缺点 |
|---------|---------|------|------|
| **密码** | 简单环境 | 配置简单 | 安全性较低，密码需加密存储 |
| **私钥** | 生产环境 | 安全性高 | 需要上传私钥到系统 |
| **SSH Agent** | 开发/运维环境 | 无需上传凭据，使用系统已有密钥 | 需要配置 SSH Agent |

## 使用 SSH Agent 认证

### 前置条件

1. **启动 SSH Agent**
   ```bash
   # 检查 SSH Agent 是否运行
   ssh-add -l

   # 如果未运行，启动 SSH Agent
   eval "$(ssh-agent -s)"
   ```

2. **添加私钥到 Agent**
   ```bash
   # 添加默认私钥
   ssh-add ~/.ssh/id_rsa

   # 或添加指定私钥
   ssh-add /path/to/your/private_key

   # 验证密钥已添加
   ssh-add -l
   ```

3. **验证 SSH 连接**
   ```bash
   # 测试能否连接目标主机
   ssh username@target-host
   ```

### 在 SmartDBA 中配置

1. 进入"主机管理"页面
2. 点击"New Host"按钮
3. 填写主机信息：
   - **名称**：给主机起个名字（如"生产服务器"）
   - **主机**：目标主机 IP 或域名
   - **端口**：SSH 端口（默认 22）
   - **用户名**：SSH 登录用户名
   - **Auth Type**：选择 **"SSH Agent"**
4. 点击"保存"

### 测试连接

保存后，点击主机列表中的"测试连接"按钮（插头图标），验证连接是否成功。

## 工作原理

当选择 SSH Agent 认证时：

1. SmartDBA 不会要求输入密码或私钥
2. 连接时，paramiko 会自动查找系统的 SSH Agent
3. SSH Agent 使用已加载的私钥进行认证
4. 私钥始终保留在本地，不会上传到 SmartDBA

## 故障排查

### 连接失败：No authentication methods available

**原因**：SSH Agent 未启动或未加载密钥

**解决**：
```bash
# 启动 SSH Agent
eval "$(ssh-agent -s)"

# 添加密钥
ssh-add ~/.ssh/id_rsa

# 验证
ssh-add -l
```

### 连接失败：Permission denied

**原因**：
1. 目标主机未配置公钥
2. 用户名错误
3. 目标主机的 `~/.ssh/authorized_keys` 权限不正确

**解决**：
```bash
# 1. 复制公钥到目标主机
ssh-copy-id username@target-host

# 2. 或手动添加公钥
cat ~/.ssh/id_rsa.pub | ssh username@target-host "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# 3. 确保权限正确
ssh username@target-host "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

### 连接失败：Host key verification failed

**原因**：目标主机未添加到 `known_hosts`

**解决**：
```bash
# 手动连接一次，接受主机密钥
ssh username@target-host

# 或使用 ssh-keyscan 添加
ssh-keyscan -H target-host >> ~/.ssh/known_hosts
```

## 安全建议

1. **使用密码保护的私钥**：即使使用 SSH Agent，私钥本身也应该设置密码保护
2. **定期轮换密钥**：定期更新 SSH 密钥对
3. **限制 Agent 转发**：不要在不信任的主机上使用 `ssh -A`
4. **使用 Ed25519 密钥**：比 RSA 更安全且更快
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

## 技术实现

### 后端修改

1. **模型层** (`backend/models/host.py`)
   - `auth_type` 字段支持 `agent` 值

2. **服务层** (`backend/services/ssh_service.py`)
   - 添加 `use_agent` 参数
   - 设置 `allow_agent=True` 和 `look_for_keys=True`

3. **连接池** (`backend/services/ssh_connection_pool.py`)
   - 支持 SSH Agent 认证方式

### 前端修改

1. **主机表单** (`frontend/js/pages/hosts.js`)
   - 添加"SSH Agent"选项
   - 显示使用说明

## 迁移说明

现有系统无需数据迁移，`auth_type` 字段已支持存储 `agent` 值。

可选：运行迁移脚本添加字段注释
```bash
python backend/migrations/add_ssh_agent_auth.py
```
