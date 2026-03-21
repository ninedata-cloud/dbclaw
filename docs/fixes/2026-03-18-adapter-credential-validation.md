# 集成管理 - 阿里云 RDS 凭证验证修复

## 问题描述

当在"集成管理"页面测试阿里云 RDS 监控数据采集时，如果没有配置 AccessKey，测试接口返回：
```json
{
  "success": true,
  "message": "采集到 0 条指标",
  "data": {
    "metrics": []
  }
}
```

这是不正确的行为，应该明确报错提示用户配置凭证。

## 根本原因

阿里云 RDS 集成模板（`backend/utils/integration_templates.py` 中的 `ALIYUN_RDS_TEMPLATE`）存在以下问题：

1. **没有验证凭证配置**：代码直接使用 `params["access_key_id"]`，如果参数为空也不会报错
2. **API 错误处理不当**：当 API 返回非 200 状态码时，代码只是跳过该数据源，不会抛出异常
3. **认证错误被忽略**：即使 AccessKey 无效导致 API 返回 400/403/404，代码也会继续执行并返回空列表

## 修复方案

修改 `backend/utils/integration_templates.py` 中的 `ALIYUN_RDS_TEMPLATE` 代码：

### 1. 添加凭证验证

在 `fetch_metrics` 函数开头添加：

```python
access_key_id = params.get("access_key_id", "")
access_key_secret = params.get("access_key_secret", "")
region_id = params.get("region_id", "cn-hangzhou")

# 验证凭证配置
if not access_key_id or not access_key_secret:
    raise ValueError("阿里云 AccessKey ID 和 AccessKey Secret 未配置，请在集成配置中设置")
```

### 2. 改进 API 错误处理

在 API 请求后添加错误处理：

```python
if response.status_code == 200:
    # 处理成功响应
    ...
else:
    # API 请求失败
    error_msg = f"阿里云 API 请求失败 (HTTP {response.status_code})"
    try:
        error_data = response.json()
        error_code = error_data.get("Code", "Unknown")
        error_message = error_data.get("Message", response.text)
        error_msg = f"阿里云 API 请求失败: {error_code} - {error_message}"
    except:
        error_msg = f"阿里云 API 请求失败 (HTTP {response.status_code}): {response.text}"

    await context.log("error", error_msg)

    # 如果是第一个请求且是认证错误，直接抛出异常
    if first_request:
        if response.status_code in (400, 403, 404):
            raise ValueError(f"阿里云 API 认证失败，请检查 AccessKey 配置: {error_msg}")
```

### 3. 添加首次请求标记

使用 `first_request` 标记来判断是否是第一个请求，如果第一个请求就失败且是认证错误，直接抛出异常：

```python
first_request = True  # 标记是否是第一个请求，用于验证凭证

for ds in datasources:
    # ... 发送请求 ...

    # 检查响应
    if response.status_code != 200:
        # 如果是第一个请求且是认证错误，直接抛出异常
        if first_request and response.status_code in (400, 403, 404):
            raise ValueError(f"阿里云 API 认证失败，请检查 AccessKey 配置: {error_msg}")

    first_request = False
```

## 修复后的行为

### 场景 1: 未配置凭证

**测试接口返回**:
```json
{
  "success": false,
  "message": "测试失败: 阿里云 AccessKey ID 和 AccessKey Secret 未配置，请在集成配置中设置"
}
```

### 场景 2: 凭证无效

**测试接口返回**:
```json
{
  "success": false,
  "message": "测试失败: 阿里云 API 认证失败，请检查 AccessKey 配置: 阿里云 API 请求失败: InvalidAccessKeyId.NotFound - ..."
}
```

### 场景 3: 凭证有效但没有配置数据源

**测试接口返回**:
```json
{
  "success": true,
  "message": "采集到 0 条指标",
  "data": {
    "metrics": []
  }
}
```

这是合理的，因为没有数据源需要采集。

## 测试验证

运行测试脚本：

```bash
python test_integration_validation.py
```

测试结果：
- ✓ 未配置凭证时抛出 ValueError
- ✓ 凭证无效时抛出 ValueError 并包含认证错误信息
- ✓ 没有数据源时返回空列表（合理行为）

## 影响范围

- 阿里云 RDS 监控数据采集集成模板
- 集成管理测试接口的错误处理
- 所有使用该集成的测试和执行流程

## 后续建议

1. **其他云厂商集成**：检查其他云厂商（腾讯云、华为云等）的集成模板，确保也有类似的凭证验证
2. **前端提示**：在前端集成测试失败时，显示更友好的错误提示
3. **文档更新**：在集成使用文档中强调凭证配置的重要性
4. **重新加载模板**：修复后需要在集成管理页面点击"加载内置模板"按钮，更新数据库中的模板代码

## 相关文件

- `backend/utils/integration_templates.py` - 阿里云 RDS 集成模板
- `backend/services/integration_service.py` - 集成测试服务
- `backend/services/integration_executor.py` - 集成执行引擎
- `test_integration_validation.py` - 测试脚本

