# 主机配置持久化功能

## 功能概述

主机配置采集后会自动保存到数据库，下次访问时优先展示缓存的配置，无需每次都通过 SSH 采集。

## 实现细节

### 1. 数据库变更

在 `host` 表中新增两个字段：
- `config_data` (JSONB): 存储主机配置信息（CPU、内存、磁盘、网络、系统信息）
- `config_collected_at` (TIMESTAMP): 配置采集时间

迁移脚本：`backend/migrations/add_host_config_cache.py`

### 2. 后端接口变更

#### GET `/api/host-detail/{host_id}/config`

**新增参数：**
- `force_refresh` (bool, 可选): 是否强制刷新，默认 false

**行为：**
1. 如果 `force_refresh=false` 且数据库中有缓存（24小时内），直接返回缓存
2. 否则通过 SSH 实时采集配置
3. 采集成功后自动保存到数据库（`config_data` 和 `config_collected_at`）

#### POST `/api/host-detail/{host_id}/config/refresh`

强制刷新主机配置（重新采集并保存），等价于 `GET /config?force_refresh=true`

### 3. 前端变更

#### 主机详情 - 信息标签页

- 页面加载时调用 `GET /config`，优先展示缓存配置
- 点击"刷新配置"按钮调用 `POST /config/refresh`，强制重新采集
- 页面底部显示配置采集时间

#### API 客户端

新增方法：
```javascript
API.refreshHostConfig(hostId)  // 强制刷新配置
```

## 缓存策略

- **缓存有效期**: 24 小时
- **自动保存**: 每次实时采集后自动保存到数据库
- **缓存失效**: 超过 24 小时或用户手动刷新

## 优势

1. **性能提升**: 避免每次访问都执行多个 SSH 命令
2. **用户体验**: 页面加载更快，配置信息即时展示
3. **降低负载**: 减少对主机的 SSH 连接和命令执行
4. **离线查看**: 即使主机暂时不可达，仍可查看历史配置

## 测试

运行验证脚本：
```bash
python tests/verify_host_fields.py
```

预期输出：
```
✓ 字段已成功添加:
  - config_collected_at: timestamp without time zone
  - config_data: jsonb
```

## 注意事项

1. 配置信息包含系统敏感信息，已通过认证保护
2. 缓存时间可根据需要调整（当前为 24 小时）
3. 首次访问或缓存过期时仍需 SSH 连接
