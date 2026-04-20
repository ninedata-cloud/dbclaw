# 加密密钥迁移指南

## 问题背景

DBClaw 使用 `ENCRYPTION_KEY` 加密存储数据库密码等敏感信息。当升级 Docker 镜像时，如果新镜像使用了不同的加密密钥，会导致无法解密旧数据，出现 `InvalidToken` 错误。

## 解决方案

从 v0.9.3 开始，DBClaw 支持**多密钥解密**机制：
- 使用当前 `ENCRYPTION_KEY` 加密新数据
- 支持使用 `LEGACY_ENCRYPTION_KEYS` 解密旧数据
- 提供迁移脚本批量重加密现有数据

## 升级步骤

### 场景 1：首次部署（推荐）

生成并固定加密密钥，避免后续升级问题：

```bash
# 生成密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 输出示例：8vQ7K3mN9pR2sT6wX1yZ4aB5cD7eF0gH1iJ2kL3mN4oP5qR6sT7uV8wX9yZ0aB1c=
```

在 `docker-compose.yml` 或 `.env` 中配置：

```yaml
environment:
  - ENCRYPTION_KEY=8vQ7K3mN9pR2sT6wX1yZ4aB5cD7eF0gH1iJ2kL3mN4oP5qR6sT7uV8wX9yZ0aB1c=
```

**重要**：请妥善保管此密钥，丢失后无法解密已加密的数据。

### 场景 2：已有部署需要升级

如果已经在使用旧版本，且外置了数据库文件，升级时需要迁移加密数据。

#### 步骤 1：获取旧密钥

从旧容器中获取当前使用的加密密钥：

```bash
# 方法 1：查看容器环境变量
docker exec <container_name> env | grep ENCRYPTION_KEY

# 方法 2：查看 docker-compose.yml 或 .env 文件
cat docker-compose.yml | grep ENCRYPTION_KEY
```

#### 步骤 2：生成新密钥

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

#### 步骤 3：配置双密钥支持

更新 `docker-compose.yml`：

```yaml
environment:
  # 新密钥（用于加密新数据）
  - ENCRYPTION_KEY=<新生成的密钥>
  # 旧密钥（用于解密旧数据，多个密钥用逗号分隔）
  - LEGACY_ENCRYPTION_KEYS=<旧容器的密钥>
```

#### 步骤 4：启动容器

```bash
docker-compose up -d
```

此时系统可以正常运行：
- 读取数据时：先用新密钥解密，失败则尝试旧密钥
- 写入数据时：始终用新密钥加密

#### 步骤 5：批量重加密（可选但推荐）

为了彻底迁移到新密钥，建议运行重加密脚本：

```bash
# 进入容器
docker exec -it <container_name> bash

# 运行迁移脚本
python backend/migrations/reencrypt_passwords.py
```

脚本会：
1. 读取所有加密的密码
2. 用旧密钥解密
3. 用新密钥重新加密
4. 更新数据库

完成后，可以移除 `LEGACY_ENCRYPTION_KEYS` 配置。

## 故障排查

### 错误：InvalidToken

**症状**：访问数据源时报错 `cryptography.fernet.InvalidToken`

**原因**：当前 `ENCRYPTION_KEY` 无法解密数据库中的密码

**解决**：
1. 检查是否配置了 `LEGACY_ENCRYPTION_KEYS`
2. 确认旧密钥是否正确
3. 运行重加密脚本

### 错误：ENCRYPTION_KEY is not configured

**症状**：启动时报错 `ENCRYPTION_KEY is not configured`

**原因**：未设置加密密钥或使用了默认占位值

**解决**：
```bash
# 生成密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 配置到环境变量
export ENCRYPTION_KEY=<生成的密钥>
```

### 重加密脚本失败

**症状**：运行 `reencrypt_passwords.py` 时部分记录解密失败

**原因**：这些记录使用了未配置的旧密钥加密

**解决**：
1. 找到所有历史使用过的密钥
2. 将它们全部添加到 `LEGACY_ENCRYPTION_KEYS`（逗号分隔）
3. 重新运行脚本

## 最佳实践

1. **首次部署时固定密钥**：避免使用镜像内置的默认密钥
2. **妥善保管密钥**：将密钥存储在安全的密钥管理系统中
3. **定期轮换密钥**：使用 `LEGACY_ENCRYPTION_KEYS` 支持平滑轮换
4. **备份数据库**：升级前务必备份外置数据库文件

## 技术细节

### 加密流程

```python
# 加密（始终使用当前密钥）
encrypted = encrypt_value(plain_password)

# 解密（自动尝试当前密钥和旧密钥）
plain_password = decrypt_value(encrypted)
```

### 密钥格式

Fernet 密钥是 44 字符的 base64 编码字符串：
```
8vQ7K3mN9pR2sT6wX1yZ4aB5cD7eF0gH1iJ2kL3mN4oP5qR6sT7uV8wX9yZ0aB1c=
```

### 多密钥配置示例

```bash
# 单个旧密钥
LEGACY_ENCRYPTION_KEYS=oldkey1==

# 多个旧密钥（按从新到旧的顺序）
LEGACY_ENCRYPTION_KEYS=oldkey2==,oldkey1==,oldkey0==
```

解密时会按顺序尝试：当前密钥 → oldkey2 → oldkey1 → oldkey0

## 相关文件

- `backend/config.py`: 配置定义
- `backend/utils/encryption.py`: 加密解密实现
- `backend/migrations/reencrypt_passwords.py`: 批量重加密脚本
