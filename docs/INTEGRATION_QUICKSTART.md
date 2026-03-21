# 外部集成管理系统 - 快速开始指南

## 概述

外部集成管理系统允许您通过编写 Python 代码对接任意第三方系统，实现告警通知、监控数据采集等功能。

## 核心概念

### Integration（集成）
一个可复用的外部对接逻辑单元，包含 Python 代码和参数定义。分为两类：
- **出站通知** (`outbound_notification`)：发送告警通知到外部系统
- **入站指标** (`inbound_metric`)：从外部系统采集监控指标

### Channel（渠道）
Integration 的实例化配置，提供具体的参数值（如 Webhook URL、API Key 等）。

## 快速开始

### 1. 使用内置模板

系统提供了 5 个内置模板，开箱即用：

1. 访问 **外部集成管理** 页面
2. 点击 **加载内置模板** 按钮
3. 系统会自动加载以下模板：
   - 飞书 Webhook 通知
   - 钉钉 Webhook 通知
   - 邮件通知
   - 通用 Webhook 通知
   - 阿里云 RDS 监控数据采集

### 2. 创建 Channel

以飞书 Webhook 为例：

1. 切换到 **Channels** 标签
2. 点击 **创建 Channel**
3. 填写信息：
   - **名称**：如"运维团队飞书群"
   - **Integration**：选择"飞书 Webhook 通知"
   - **Webhook URL**：填写飞书机器人的 Webhook 地址
   - **签名密钥**（可选）：如果启用了签名验证，填写密钥
4. 点击 **保存**

### 3. 在告警订阅中使用

1. 访问 **告警管理** 页面
2. 创建或编辑告警订阅
3. 在通知渠道中选择刚创建的 Channel
4. 保存订阅

现在，当告警触发时，系统会自动通过飞书发送通知！

## 测试 Integration

在创建 Channel 之前，可以先测试 Integration 是否正常工作：

1. 在 Integration 列表中找到要测试的 Integration
2. 点击 **测试** 按钮（🧪）
3. 填写测试参数
4. 点击 **执行测试**
5. 查看测试结果

## 创建自定义 Integration

如果内置模板不满足需求，可以创建自定义 Integration：

### 出站通知示例

```python
async def send_notification(context, params, payload):
    """
    发送通知

    Args:
        context: IntegrationContext 对象，提供工具方法
        params: dict，来自 Channel 的实例化参数
        payload: dict，通知内容
            - title: str
            - content: str
            - severity: str (critical/warning/info)
            - datasource_name: str
            - alert_id: int
            - timestamp: str

    Returns:
        dict: {"success": bool, "message": str}
    """
    webhook_url = params["webhook_url"]

    # 构建消息
    message = {
        "title": payload["title"],
        "content": payload["content"],
        "severity": payload["severity"]
    }

    # 发送 HTTP 请求
    response = await context.http_request("POST", webhook_url, json=message)

    if response.status_code == 200:
        return {"success": True, "message": "发送成功"}
    else:
        return {"success": False, "message": f"发送失败: {response.text}"}
```

### 入站指标示例

```python
async def fetch_metrics(context, params, datasources):
    """
    采集指标

    Args:
        context: IntegrationContext 对象
        params: dict，来自 Channel 的实例化参数
        datasources: list[dict]，关联的数据源列表

    Returns:
        list[dict]: MetricPoint 列表
            - datasource_id: int
            - metric_name: str
            - metric_value: float
            - timestamp: str (ISO 8601)
            - labels: dict (可选)
    """
    api_url = params["api_url"]
    api_key = params["api_key"]

    metrics = []

    for ds in datasources:
        # 调用外部 API
        response = await context.http_request(
            "GET",
            f"{api_url}/metrics",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        if response.status_code == 200:
            data = response.json()
            metrics.append({
                "datasource_id": ds["id"],
                "metric_name": "cpu_usage",
                "metric_value": data["cpu"],
                "timestamp": data["timestamp"],
                "labels": {"source": "external_api"}
            })

    return metrics
```

## IntegrationContext API

在 Integration 代码中可以使用以下工具方法：

### HTTP 请求
```python
response = await context.http_request("POST", url, json=data, headers=headers)
# response.status_code
# response.text
# response.json()
```

### 读取系统配置
```python
smtp_host = await context.get_system_config("smtp_host")
```

### 加密/解密
```python
encrypted = await context.encrypt("sensitive_data")
decrypted = await context.decrypt(encrypted)
```

### 记录日志
```python
await context.log("info", "Processing started")
await context.log("error", "Failed to connect")
```

### 查询数据源
```python
datasource = await context.get_datasource(datasource_id)
# datasource["name"], datasource["host"], etc.
```

## 参数 Schema 定义

使用 JSON Schema 格式定义参数：

```json
{
  "type": "object",
  "properties": {
    "webhook_url": {
      "type": "string",
      "title": "Webhook URL",
      "description": "目标 Webhook 地址"
    },
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "认证密钥",
      "format": "password"
    },
    "timeout": {
      "type": "integer",
      "title": "超时时间（秒）",
      "default": 30
    }
  },
  "required": ["webhook_url", "api_key"]
}
```

前端会根据 Schema 自动生成表单：
- `format: "password"` 的字段会自动加密
- `required` 数组中的字段为必填项
- `default` 值会作为占位符显示

## 常见问题

### Q: 如何调试 Integration 代码？

A: 使用 `context.log()` 记录日志，日志会写入应用日志文件。也可以使用测试功能验证代码逻辑。

### Q: 敏感信息如何保护？

A: 在创建 Channel 时，密码字段会自动加密存储。在代码中使用 `context.encrypt()` 和 `context.decrypt()` 处理敏感信息。

### Q: Integration 执行超时怎么办？

A: 默认超时时间为 30 秒。如果需要更长时间，可以优化代码逻辑，或者将长时间操作拆分为多个步骤。

### Q: 可以导入第三方 Python 库吗？

A: 可以。Integration 代码以完整权限执行，可以导入任何已安装的 Python 库。

### Q: 如何处理错误？

A: 在代码中使用 try-except 捕获异常，并返回 `{"success": False, "message": "错误信息"}`。系统会自动记录执行日志。

## 最佳实践

1. **测试先行**：创建 Channel 之前先测试 Integration
2. **参数化配置**：将可变的值（URL、密钥等）定义为参数，不要硬编码
3. **错误处理**：添加适当的错误处理和日志记录
4. **超时控制**：避免长时间阻塞操作
5. **安全意识**：不要在代码中硬编码敏感信息

## 获取帮助

如有问题，请查看：
- 系统日志：`/var/log/dbguard/app.log`
- 执行日志：在 Integration 管理页面查看执行历史
- 技术文档：`docs/INTEGRATION_SYSTEM_IMPLEMENTATION.md`
