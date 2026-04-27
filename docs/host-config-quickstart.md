# 主机配置功能 - 快速启动指南

## 启动应用

```bash
# 1. 确保虚拟环境已激活
source .venv/bin/activate

# 2. 启动应用
python run.py
```

## 访问功能

1. 打开浏览器访问：`http://localhost:8000`
2. 登录系统（默认用户名：admin，密码：见 .env 配置）
3. 导航到主机详情页面：
   - 方式一：点击左侧菜单"主机管理" → 点击任意主机进入详情
   - 方式二：直接访问 `http://localhost:8000/#host-detail?host=1`

4. 在主机详情页面，点击"主机配置"标签页

## 功能演示

### 查看主机配置
- 系统会自动通过 SSH 连接主机
- 执行系统命令获取配置信息
- 展示 CPU、内存、磁盘、网络等详细配置

### 刷新配置
- 点击右上角"刷新配置"按钮
- 重新获取最新的主机配置信息

## API 测试

### 使用 curl 测试

```bash
# 获取主机配置（需要先登录获取 token）
curl -X GET "http://localhost:8000/api/host-detail/1/config" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 使用 Python 测试

```python
import requests

# 登录
login_response = requests.post(
    "http://localhost:8000/api/auth/login",
    json={"username": "admin", "password": "your_password"}
)
token = login_response.json()["access_token"]

# 获取主机配置
config_response = requests.get(
    "http://localhost:8000/api/host-detail/1/config",
    headers={"Authorization": f"Bearer {token}"}
)
config = config_response.json()

print("CPU 核心数:", config["cpu"]["cores"])
print("总内存:", config["memory"]["MemTotal"])
print("磁盘数量:", len(config["disk"]))
```

## 运行测试

```bash
# 运行主机配置 API 测试
python -m pytest tests/test_host_config_api.py -v

# 运行所有测试
python -m pytest tests/ -v
```

## 故障排查

### 问题：无法获取主机配置

**可能原因**：
1. SSH 连接未配置或连接失败
2. SSH 用户权限不足
3. 主机不支持某些命令

**解决方法**：
1. 检查主机 SSH 连接配置
2. 确保 SSH 用户有读取 `/proc` 和 `/etc` 的权限
3. 查看后端日志了解具体错误信息

### 问题：部分配置信息显示为空

**可能原因**：
- 某些系统命令执行失败
- 命令输出格式不符合预期

**解决方法**：
- 这是正常现象，系统会优雅降级
- 可用的配置信息仍会正常显示

### 问题：页面加载缓慢

**可能原因**：
- SSH 连接建立较慢
- 主机响应较慢

**解决方法**：
- 等待加载完成（最多 10 秒超时）
- 检查网络连接质量
- 考虑添加配置缓存机制

## 开发调试

### 查看后端日志

```bash
# 启动应用时会输出日志
python run.py

# 查看特定日志
tail -f logs/app.log  # 如果配置了日志文件
```

### 前端调试

1. 打开浏览器开发者工具（F12）
2. 切换到 Console 标签查看 JavaScript 日志
3. 切换到 Network 标签查看 API 请求

### 修改代码后重启

```bash
# Ctrl+C 停止应用
# 重新启动
python run.py
```

## 性能优化建议

1. **添加缓存**：配置信息变化不频繁，可以缓存 5-10 分钟
2. **并行执行**：多个命令可以并行执行以提高速度
3. **按需加载**：只在用户点击标签页时才获取配置

## 安全注意事项

1. ✅ 仅执行只读命令，不会修改主机配置
2. ✅ 命令执行有超时保护
3. ✅ 使用 SSH 连接池，避免连接泄漏
4. ⚠️ 确保 SSH 用户权限最小化
5. ⚠️ 定期审计执行的命令列表

## 相关文档

- [功能说明文档](./host-config-feature.md)
- [实现总结文档](./host-config-implementation-summary.md)
- [主项目 README](../README.md)

## 技术支持

如有问题，请查看：
1. 后端日志文件
2. 浏览器控制台错误信息
3. SSH 连接状态
4. 主机系统日志
