# 阿里云 RDS 集成 - 从系统配置读取 AccessKey

## 改动说明

将阿里云 AccessKey 从集成测试界面输入改为从系统配置中读取，提高安全性。

## 修改内容

### 1. 集成模板配置 Schema

**文件**: `backend/utils/integration_templates.py`

移除 `access_key_id` 和 `access_key_secret` 参数，只保留 `region_id`：

```python
"config_schema": {
    "type": "object",
    "properties": {
        "region_id": {
            "type": "string",
            "title": "地域 ID",
            "default": "cn-hangzhou",
            "description": "阿里云地域 ID，如 cn-hangzhou"
        }
    },
    "required": ["region_id"]
}
```

### 2. 集成代码逻辑

**文件**: `backend/utils/integration_templates.py`

从系统配置中读取 AccessKey：

```python
async def fetch_metrics(context, params, datasources):
    # 从系统配置中读取阿里云凭证
    access_key_id = await context.get_system_config("aliyun_access_key_id")
    access_key_secret = await context.get_system_config("aliyun_access_key_secret")

    # 验证凭证配置
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云 AccessKey 未配置，请在系统配置中设置 aliyun_access_key_id 和 aliyun_access_key_secret")

    # 从参数中获取地域 ID
    region_id = params.get("region_id", "cn-hangzhou")
    # ...
```

### 3. 系统配置初始化

**文件**: `backend/app.py`

添加阿里云配置项的初始化：

```python
# Seed default Aliyun configs
aliyun_defaults = [
    ("aliyun_access_key_id", "", "string", "阿里云 AccessKey ID（用于 RDS 监控数据采集）"),
    ("aliyun_access_key_secret", "", "string", "阿里云 AccessKey Secret（用于 RDS 监控数据采集）"),
]

# Seed Aliyun configs
for key, default_val, val_type, desc in aliyun_defaults:
    _exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == key))
    if not _exists.scalar_one_or_none():
        await _config_service.set_config(
            _db, key=key, value=default_val,
            value_type=val_type, description=desc,
            category="integration"
        )
```

## 使用步骤

### 1. 配置阿里云 AccessKey

在"系统配置"页面，找到"集成"分类，配置：
- `aliyun_access_key_id`: 阿里云 AccessKey ID
- `aliyun_access_key_secret`: 阿里云 AccessKey Secret

### 2. 测试集成

在"集成管理"页面：
1. 选择"阿里云 RDS 监控数据采集"
2. 点击"测试"按钮
3. 选择数据源（需要配置 external_instance_id）
4. 输入地域 ID（默认 cn-hangzhou）
5. 执行测试

### 3. 错误提示

如果未配置 AccessKey，会提示：
```
测试失败: 阿里云 AccessKey 未配置，请在系统配置中设置 aliyun_access_key_id 和 aliyun_access_key_secret
```

## 优势

1. **安全性提高**：AccessKey 不在界面上明文输入，统一在系统配置中管理
2. **使用便捷**：配置一次，所有测试和执行都使用同一套凭证
3. **权限控制**：只有管理员可以修改系统配置，普通用户无法看到 AccessKey
4. **审计追踪**：系统配置的修改可以记录日志

## 部署步骤

1. 修改代码（app.py、integration_templates.py）
2. 重启服务（会自动创建新的系统配置项）
3. 在系统配置页面配置阿里云 AccessKey
4. 在集成管理页面点击"加载内置模板"更新模板
5. 测试验证

## 相关文件

- `backend/app.py` - 系统配置初始化
- `backend/utils/integration_templates.py` - 阿里云 RDS 集成模板
