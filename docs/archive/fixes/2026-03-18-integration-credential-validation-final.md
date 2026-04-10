# 集成管理 - 阿里云 RDS 凭证验证修复（最终版）

## 问题描述

在"集成管理"页面测试阿里云 RDS 监控数据采集时，即使随便输入 AccessKey，测试接口仍然返回：
```json
{
  "success": true,
  "message": "采集到 0 条指标",
  "data": {
    "metrics": []
  }
}
```

## 根本原因

阿里云 RDS 集成模板存在以下问题：

1. **只在有数据源时才发送 API 请求**：如果测试时查询到的数据源没有配置 `external_instance_id`，代码会跳过所有数据源，不发送任何 API 请求
2. **没有主动验证凭证**：代码依赖于实际的 API 请求来间接验证凭证，如果没有发送请求就无法验证
3. **测试接口的数据源选择问题**：测试接口随机选择一个数据源，这个数据源可能没有配置 `external_instance_id`

## 修复方案

在 `backend/utils/integration_templates.py` 的 `ALIYUN_RDS_TEMPLATE` 中添加主动凭证验证：

### 1. 在 fetch_metrics 开头添加凭证验证

```python
async def fetch_metrics(context, params, datasources):
    access_key_id = params.get("access_key_id", "")
    access_key_secret = params.get("access_key_secret", "")
    region_id = params.get("region_id", "cn-hangzhou")

    # 验证凭证配置
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云 AccessKey ID 和 AccessKey Secret 未配置，请在集成配置中设置")

    # 验证凭证有效性（发送一个测试请求）
    await _validate_credentials(context, access_key_id, access_key_secret, region_id)

    # ... 后续采集逻辑 ...
```

### 2. 添加独立的凭证验证函数

```python
async def _validate_credentials(context, access_key_id, access_key_secret, region_id):
    """验证阿里云凭证有效性"""
    # 发送一个简单的 API 请求来验证凭证
    end_time = datetime.utcnow()

    common_params = {
        "Format": "JSON",
        "Version": "2014-08-15",
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "Timestamp": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": str(int(time.time() * 1000)),
        "Action": "DescribeDBInstances",
        "PageSize": "1"
    }

    # 签名
    sorted_params = sorted(common_params.items())
    query_string = "&".join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted_params])
    string_to_sign = f"GET&%2F&{urllib.parse.quote(query_string, safe='')}"
    signature = base64.b64encode(hmac.new(
        (access_key_secret + "&").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1
    ).digest()).decode("utf-8")

    common_params["Signature"] = signature

    # 发送请求
    url = f"https://rds.{region_id}.aliyuncs.com/"
    response = await context.http_request("GET", url, params=common_params)

    if response.status_code != 200:
        # 凭证验证失败
        error_msg = f"阿里云 API 认证失败 (HTTP {response.status_code})"
        try:
            error_data = response.json()
            error_code = error_data.get("Code", "Unknown")
            error_message = error_data.get("Message", response.text)
            error_msg = f"{error_code}: {error_message}"
        except:
            error_msg = f"HTTP {response.status_code}: {response.text}"

        raise ValueError(f"阿里云 AccessKey 验证失败，请检查配置: {error_msg}")

    await context.log("info", "阿里云凭证验证成功")
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

### 场景 2: 随便输入的 AccessKey

**测试接口返回**:
```json
{
  "success": false,
  "message": "测试失败: 阿里云 AccessKey 验证失败，请检查配置: InvalidAccessKeyId.NotFound: Specified access key is not found."
}
```

### 场景 3: 没有数据源或数据源没有 external_instance_id

**测试接口返回**:
```json
{
  "success": false,
  "message": "测试失败: 阿里云 AccessKey 验证失败，请检查配置: ..."
}
```

即使没有数据源，也会先验证凭证，所以无效凭证会被检测到。

### 场景 4: 凭证有效且有配置好的数据源

**测试接口返回**:
```json
{
  "success": true,
  "message": "采集到 N 条指标",
  "data": {
    "metrics": [...]
  }
}
```

## 关键改进

1. **主动验证而非被动验证**：不依赖于实际的指标采集请求，而是在开始时就发送一个专门的验证请求
2. **使用轻量级 API**：使用 `DescribeDBInstances` API（只查询 1 条记录）来验证凭证，比实际的指标采集请求更快
3. **无论数据源状态都会验证**：即使没有数据源或数据源配置不完整，也会验证凭证

## 测试验证

运行测试脚本：

```bash
python test_integration_validation.py
```

测试结果：
- ✓ 未配置凭证时抛出 ValueError
- ✓ 随便输入的 AccessKey 会被检测为无效
- ✓ 没有数据源时也会验证凭证
- ✓ 数据源没有 external_instance_id 时也会验证凭证

## 部署步骤

1. 修改 `backend/utils/integration_templates.py` 中的 `ALIYUN_RDS_TEMPLATE`
2. 重启后端服务
3. 在集成管理页面点击"加载内置模板"按钮，更新数据库中的模板代码
4. 测试验证

## 影响范围

- 阿里云 RDS 监控数据采集集成模板
- 集成管理测试接口的错误处理
- 所有使用该集成的测试和执行流程

## 相关文件

- `backend/utils/integration_templates.py` - 阿里云 RDS 集成模板
- `backend/services/integration_service.py` - 集成测试服务
- `backend/services/integration_executor.py` - 集成执行引擎
- `test_integration_validation.py` - 测试脚本
