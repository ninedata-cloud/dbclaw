"""
内置 Integration 模板定义
"""

# 飞书 Webhook 模板
FEISHU_WEBHOOK_TEMPLATE = {
    "integration_id": "builtin_feishu_webhook",
    "name": "飞书 Webhook 通知",
    "description": "通过飞书 Webhook 发送交互式卡片通知",
    "integration_type": "outbound_notification",
    "category": "im",
    "config_schema": {
        "type": "object",
        "properties": {
            "webhook_url": {
                "type": "string",
                "title": "Webhook URL",
                "description": "飞书机器人 Webhook 地址"
            },
            "secret": {
                "type": "string",
                "title": "签名密钥（可选）",
                "description": "飞书机器人签名密钥，用于验证请求",
                "format": "password"
            }
        },
        "required": ["webhook_url"]
    },
    "code": "import time\nimport hmac\nimport hashlib\nimport base64\n\nasync def send_notification(context, params, payload):\n    webhook_url = params.get(\"webhook_url\")\n    secret = params.get(\"secret\")\n\n    severity_colors = {\n        \"critical\": \"red\",\n        \"high\": \"red\",\n        \"warning\": \"orange\",\n        \"medium\": \"orange\",\n        \"low\": \"yellow\",\n        \"info\": \"blue\"\n    }\n    severity_labels = {\n        \"critical\": \"严重\",\n        \"high\": \"高\",\n        \"warning\": \"中\",\n        \"medium\": \"中\",\n        \"low\": \"低\",\n        \"info\": \"提示\"\n    }\n    color = severity_colors.get(payload.get(\"severity\", \"\"), \"blue\")\n    severity_label = severity_labels.get(payload.get(\"severity\", \"\"), payload.get(\"severity\", \"\"))\n\n    elements = []\n\n    # === 告警信息 ===\n    alert_lines = [\n        f\"**告警类型：** {payload.get('alert_type', '未知')}\",\n        f\"**严重程度：** {severity_label}\",\n    ]\n    metric_name = payload.get(\"metric_name\")\n    metric_value = payload.get(\"metric_value\")\n    threshold_value = payload.get(\"threshold_value\")\n    if metric_name:\n        if metric_value is not None:\n            alert_lines.append(f\"**指标：** {metric_name} = {metric_value:.2f}\")\n        else:\n            alert_lines.append(f\"**指标：** {metric_name}\")\n    if threshold_value is not None:\n        alert_lines.append(f\"**阈值：** {threshold_value:.2f}\")\n    if payload.get(\"trigger_reason\"):\n        alert_lines.append(f\"**触发原因：** {payload.get('trigger_reason')}\")\n    alert_lines.append(f\"**触发时间：** {payload.get('timestamp', '')}\")\n    elements.append({\"tag\": \"div\", \"text\": {\"tag\": \"lark_md\", \"content\": \"\\n\".join(alert_lines)}})\n\n    # === AI 诊断 ===\n    ai_summary = payload.get(\"ai_diagnosis_summary\")\n    root_cause = payload.get(\"root_cause\")\n    recommended_actions = payload.get(\"recommended_actions\")\n    diagnosis_status = payload.get(\"diagnosis_status\") or \"\"\n\n    if ai_summary or root_cause or recommended_actions:\n        elements.append({\"tag\": \"hr\"})\n        diag_status_label = {\"pending\": \"诊断中\", \"in_progress\": \"诊断中\", \"completed\": \"已完成\", \"failed\": \"失败\"}.get(diagnosis_status, diagnosis_status or \"\")\n        elements.append({\n            \"tag\": \"div\",\n            \"text\": {\"tag\": \"lark_md\", \"content\": \"**AI 诊断**\" + (f\"（{diag_status_label}）\" if diag_status_label else \"\")}\n        })\n        if ai_summary:\n            elements.append({\"tag\": \"div\", \"text\": {\"tag\": \"lark_md\", \"content\": \"**&#x1F4AC; 诊断摘要**\\n\" + ai_summary[:300]}})\n        if root_cause:\n            elements.append({\"tag\": \"div\", \"text\": {\"tag\": \"lark_md\", \"content\": \"**&#x1F50D; 根本原因**\\n\" + root_cause[:500]}})\n        if recommended_actions:\n            elements.append({\"tag\": \"div\", \"text\": {\"tag\": \"lark_md\", \"content\": \"**&#x1F6E0; 处置建议**\\n\" + recommended_actions[:500]}})\n\n    # === 操作按钮 ===\n    actions = []\n    if payload.get(\"alert_url\"):\n        actions.append({\"tag\": \"button\", \"text\": {\"tag\": \"plain_text\", \"content\": \"查看告警详情\"}, \"type\": \"primary\", \"multi_url\": {\"url\": payload[\"alert_url\"], \"pc_url\": payload[\"alert_url\"], \"android_url\": payload[\"alert_url\"], \"ios_url\": payload[\"alert_url\"]}})\n    if payload.get(\"report_url\"):\n        actions.append({\"tag\": \"button\", \"text\": {\"tag\": \"plain_text\", \"content\": \"查看诊断报告\"}, \"type\": \"default\", \"multi_url\": {\"url\": payload[\"report_url\"], \"pc_url\": payload[\"report_url\"], \"android_url\": payload[\"report_url\"], \"ios_url\": payload[\"report_url\"]}})\n    if actions:\n        elements.append({\"tag\": \"action\", \"actions\": actions})\n\n    card = {\n        \"msg_type\": \"interactive\",\n        \"card\": {\n            \"config\": {\"wide_screen_mode\": True},\n            \"header\": {\"title\": {\"tag\": \"plain_text\", \"content\": payload[\"title\"]}, \"template\": color},\n            \"elements\": elements\n        }\n    }\n\n    headers = {\"Content-Type\": \"application/json\"}\n    if secret:\n        timestamp = str(int(time.time()))\n        sign_string = timestamp + \"\\n\" + secret\n        sign = base64.b64encode(hmac.new(sign_string.encode(\"utf-8\"), digestmod=hashlib.sha256).digest()).decode(\"utf-8\")\n        card[\"timestamp\"] = timestamp\n        card[\"sign\"] = sign\n\n    response = await context.http_request(\"POST\", webhook_url, json=card, headers=headers)\n    if response.status_code == 200:\n        return {\"success\": True, \"message\": \"飞书通知发送成功\"}\n    else:\n        return {\"success\": False, \"message\": \"飞书通知发送失败: \" + response.text}\n"
}

# 钉钉 Webhook 模板
DINGTALK_WEBHOOK_TEMPLATE = {
    "integration_id": "builtin_dingtalk_webhook",
    "name": "钉钉 Webhook 通知",
    "description": "通过钉钉 Webhook 发送 Markdown 消息",
    "integration_type": "outbound_notification",
    "category": "im",
    "config_schema": {
        "type": "object",
        "properties": {
            "webhook_url": {
                "type": "string",
                "title": "Webhook URL",
                "description": "钉钉机器人 Webhook 地址"
            },
            "secret": {
                "type": "string",
                "title": "签名密钥",
                "description": "钉钉机器人签名密钥",
                "format": "password"
            }
        },
        "required": ["webhook_url"]
    },
    "code": "import time\nimport hmac\nimport hashlib\nimport base64\nimport urllib.parse\n\nasync def send_notification(context, params, payload):\n    webhook_url = params[\"webhook_url\"]\n    secret = params.get(\"secret\")\n\n    severity_emoji = {\"critical\": \"&#x1F534;\", \"warning\": \"&#x1F7E0;\", \"info\": \"&#x1F535;\"}\n    emoji = severity_emoji.get(payload[\"severity\"], \"\")\n\n    markdown_parts = [\"### \" + emoji + \" \" + payload[\"title\"], \"\", payload[\"content\"]]\n\n    # 添加诊断分析\n    if payload.get(\"root_cause\"):\n        markdown_parts.extend([\"\", \"> **&#x1F50D; 根本原因**\", \"> \" + payload[\"root_cause\"][:500]])\n    if payload.get(\"recommended_actions\"):\n        markdown_parts.extend([\"\", \"> **&#x1F6E0; 处置建议**\", \"> \" + payload[\"recommended_actions\"][:500]])\n\n    markdown_parts.extend([\"\", \"---\", \"**数据源**: \" + payload[\"datasource_name\"], \"**时间**: \" + payload[\"timestamp\"]])\n\n    message = {\"msgtype\": \"markdown\", \"markdown\": {\"title\": payload[\"title\"], \"text\": \"\\n\".join(markdown_parts)}}\n\n    signed_url = webhook_url\n    if secret:\n        timestamp = str(int(time.time() * 1000))\n        sign_string = timestamp + \"\\n\" + secret\n        sign = base64.b64encode(hmac.new(secret.encode(\"utf-8\"), sign_string.encode(\"utf-8\"), digestmod=hashlib.sha256).digest()).decode(\"utf-8\")\n        signed_url = webhook_url + \"&timestamp=\" + timestamp + \"&sign=\" + urllib.parse.quote(sign)\n\n    response = await context.http_request(\"POST\", signed_url, json=message)\n    if response.status_code == 200:\n        result = response.json()\n        if result.get(\"errcode\") == 0:\n            return {\"success\": True, \"message\": \"钉钉通知发送成功\"}\n        else:\n            return {\"success\": False, \"message\": \"钉钉通知发送失败: \" + result.get(\"errmsg\")}\n    else:\n        return {\"success\": False, \"message\": \"钉钉通知发送失败: \" + response.text}\n"
}

# 邮件通知模板
EMAIL_TEMPLATE = {
    "integration_id": "builtin_email",
    "name": "邮件通知",
    "description": "通过 SMTP 发送 HTML 格式邮件",
    "integration_type": "outbound_notification",
    "category": "email",
    "config_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "title": "收件人",
                "description": "收件人邮箱地址，多个用逗号分隔"
            },
            "cc": {
                "type": "string",
                "title": "抄送（可选）",
                "description": "抄送邮箱地址，多个用逗号分隔"
            }
        },
        "required": ["to"]
    },
    "code": "import smtplib\nimport asyncio\nfrom email.mime.text import MIMEText\nfrom email.mime.multipart import MIMEMultipart\n\nasync def send_notification(context, params, payload):\n    smtp_host = await context.get_system_config(\"smtp_host\")\n    smtp_port = await context.get_system_config(\"smtp_port\")\n    smtp_username = await context.get_system_config(\"smtp_username\")\n    smtp_password = await context.get_system_config(\"smtp_password\")\n    smtp_from_email = await context.get_system_config(\"smtp_from_email\")\n    smtp_use_tls = await context.get_system_config(\"smtp_use_tls\")\n\n    if not all([smtp_host, smtp_port, smtp_username, smtp_password, smtp_from_email]):\n        return {\"success\": False, \"message\": \"SMTP 配置不完整，请在系统配置中设置\"}\n\n    msg = MIMEMultipart(\"alternative\")\n    msg[\"Subject\"] = payload[\"title\"]\n    msg[\"From\"] = smtp_from_email\n    msg[\"To\"] = params[\"to\"]\n    if params.get(\"cc\"):\n        msg[\"Cc\"] = params[\"cc\"]\n\n    severity_colors = {\"critical\": \"#ff4d4f\", \"warning\": \"#faad14\", \"info\": \"#1890ff\"}\n    border_color = severity_colors.get(payload[\"severity\"], \"#1890ff\")\n    content_html = payload[\"content\"].replace(\"<\", \"&lt;\").replace(\">\", \"&gt;\").replace(\"\\n\", \"<br>\")\n\n    # 构建诊断分析 HTML\n    diagnosis_html = \"\"\n    if payload.get(\"root_cause\"):\n        rc = payload[\"root_cause\"].replace(\"<\", \"&lt;\").replace(\">\", \"&gt;\").replace(\"\\n\", \"<br>\")[:500]\n        diagnosis_html += '<div style=\"margin-bottom:12px;padding:10px;background:#f0f7ff;border-left:3px solid #1890ff;border-radius:4px;\"><p style=\"margin:0 0 4px 0;font-weight:bold;color:#1890ff;\">&#x1F50D; 根本原因</p><p style=\"margin:0;color:#333;line-height:1.6;\">' + rc + '</p></div>'\n    if payload.get(\"recommended_actions\"):\n        ra = payload[\"recommended_actions\"].replace(\"<\", \"&lt;\").replace(\">\", \"&gt;\").replace(\"\\n\", \"<br>\")[:500]\n        diagnosis_html += '<div style=\"margin-bottom:12px;padding:10px;background:#f6ffed;border-left:3px solid #52c41a;border-radius:4px;\"><p style=\"margin:0 0 4px 0;font-weight:bold;color:#52c41a;\">&#x1F6E0; 处置建议</p><p style=\"margin:0;color:#333;line-height:1.6;\">' + ra + '</p></div>'\n\n    html = '<html><body style=\"font-family:Arial,sans-serif;\"><div style=\"border-left:4px solid ' + border_color + ';padding-left:16px;\"><h2>' + payload[\"title\"] + '</h2><p>' + content_html + '</p>' + diagnosis_html + '<hr><p><strong>数据源:</strong> ' + payload[\"datasource_name\"] + '</p><p><strong>时间:</strong> ' + payload[\"timestamp\"] + '</p></div></body></html>'\n\n    msg.attach(MIMEText(html, \"html\"))\n\n    def send_email_sync():\n        server = None\n        try:\n            port = int(smtp_port)\n            if port == 465 or smtp_use_tls == \"ssl\":\n                server = smtplib.SMTP_SSL(smtp_host, port, timeout=20)\n            else:\n                server = smtplib.SMTP(smtp_host, port, timeout=20)\n                if smtp_use_tls == \"true\":\n                    server.starttls()\n            server.login(smtp_username, smtp_password)\n            recipients = [r.strip() for r in params[\"to\"].split(\",\")]\n            if params.get(\"cc\"):\n                recipients.extend([r.strip() for r in params[\"cc\"].split(\",\")])\n            server.sendmail(smtp_from_email, recipients, msg.as_string())\n            return {\"success\": True, \"message\": \"邮件发送成功\"}\n        except smtplib.SMTPAuthenticationError as e:\n            return {\"success\": False, \"message\": \"SMTP 认证失败: \" + str(e)}\n        except smtplib.SMTPConnectError as e:\n            return {\"success\": False, \"message\": \"无法连接 SMTP 服务器: \" + str(e)}\n        except TimeoutError:\n            return {\"success\": False, \"message\": \"连接 SMTP 服务器超时\"}\n        except Exception as e:\n            return {\"success\": False, \"message\": \"邮件发送失败: \" + type(e).__name__ + \": \" + str(e)}\n        finally:\n            if server:\n                try:\n                    server.quit()\n                except:\n                    pass\n\n    loop = asyncio.get_event_loop()\n    result = await loop.run_in_executor(_thread_pool, send_email_sync)\n    return result\n"
}

# 通用 Webhook 模板
GENERIC_WEBHOOK_TEMPLATE = {
    "integration_id": "builtin_generic_webhook",
    "name": "通用 Webhook 通知",
    "description": "发送 JSON 格式的 HTTP 请求到任意 Webhook 地址",
    "integration_type": "outbound_notification",
    "category": "webhook",
    "config_schema": {
        "type": "object",
        "properties": {
            "webhook_url": {
                "type": "string",
                "title": "Webhook URL",
                "description": "目标 Webhook 地址"
            },
            "method": {
                "type": "string",
                "title": "HTTP 方法",
                "enum": ["POST", "PUT"],
                "default": "POST"
            },
            "auth_type": {
                "type": "string",
                "title": "认证方式",
                "enum": ["none", "bearer", "basic"],
                "default": "none"
            },
            "auth_token": {
                "type": "string",
                "title": "认证 Token（可选）",
                "format": "password"
            }
        },
        "required": ["webhook_url"]
    },
    "code": "async def send_notification(context, params, payload):\n    webhook_url = params[\"webhook_url\"]\n    method = params.get(\"method\", \"POST\")\n    auth_type = params.get(\"auth_type\", \"none\")\n    auth_token = params.get(\"auth_token\")\n\n    headers = {\"Content-Type\": \"application/json\"}\n    if auth_type == \"bearer\" and auth_token:\n        headers[\"Authorization\"] = \"Bearer \" + auth_token\n    elif auth_type == \"basic\" and auth_token:\n        headers[\"Authorization\"] = \"Basic \" + auth_token\n\n    webhook_payload = {\n        \"title\": payload[\"title\"],\n        \"content\": payload[\"content\"],\n        \"severity\": payload[\"severity\"],\n        \"datasource_name\": payload[\"datasource_name\"],\n        \"alert_id\": payload[\"alert_id\"],\n        \"timestamp\": payload[\"timestamp\"],\n        \"ai_diagnosis_summary\": payload.get(\"ai_diagnosis_summary\"),\n        \"root_cause\": payload.get(\"root_cause\"),\n        \"recommended_actions\": payload.get(\"recommended_actions\"),\n        \"diagnosis_status\": payload.get(\"diagnosis_status\"),\n        \"alert_url\": payload.get(\"alert_url\"),\n        \"report_url\": payload.get(\"report_url\"),\n    }\n\n    response = await context.http_request(method, webhook_url, json=webhook_payload, headers=headers)\n    if 200 <= response.status_code < 300:\n        return {\"success\": True, \"message\": \"Webhook 通知发送成功 (HTTP \" + str(response.status_code) + \")\"}\n    else:\n        return {\"success\": False, \"message\": \"Webhook 通知发送失败: HTTP \" + str(response.status_code) + \", \" + response.text}\n"
}

# 阿里云 RDS 监控数据采集模板
ALIYUN_RDS_TEMPLATE = {
    "integration_id": "builtin_aliyun_rds",
    "name": "阿里云 RDS 监控数据采集",
    "description": "从阿里云 RDS API 采集监控指标，AccessKey 从系统配置中读取",
    "integration_type": "inbound_metric",
    "category": "monitoring",
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
    },
    "code": """
async def fetch_metrics(context, params, datasources):
    access_key_id = await context.get_system_config("aliyun_access_key_id")
    access_key_secret = await context.get_system_config("aliyun_access_key_secret")
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云 AccessKey 未配置，请在系统配置中设置 aliyun_access_key_id 和 aliyun_access_key_secret")
    region_id = params.get("region_id", "cn-hangzhou")
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkrds.request.v20140815 import DescribeDBInstancePerformanceRequest
    except ImportError:
        raise ValueError("阿里云 SDK 未安装，请运行: pip install aliyun-python-sdk-core aliyun-python-sdk-rds")
    from datetime import datetime, timedelta
    import json
    client = AcsClient(access_key_id, access_key_secret, region_id)
    metrics = []
    metric_mappings = {
        "MySQL_MemCpuUsage": [("cpu_usage", 0, "%"), ("memory_usage", 1, "%")],
        "MySQL_DetailedSpaceUsage": [("disk_total", 0, "MB"), ("disk_data", 1, "MB"), ("disk_log", 2, "MB"), ("disk_temp", 3, "MB"), ("disk_system", 4, "MB")],
        "MySQL_IOPS": [("disk_reads_per_sec", 0, "次/秒"), ("disk_writes_per_sec", 0, "次/秒")],
        "MySQL_NetworkTraffic": [("network_rx_bytes", 0, "KB/秒"), ("network_tx_bytes", 1, "KB/秒")],
        "MySQL_QPSTPS": [("qps", 0, "次/秒"), ("tps", 1, "个/秒")],
        "MySQL_Sessions": [("connections_active", 0, "个"), ("connections_total", 1, "个")]
    }
    for ds in datasources:
        instance_id = ds.get("external_instance_id")
        if not instance_id:
            raise ValueError("数据源 " + ds["name"] + " 未配置 external_instance_id")
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            keys = ",".join(metric_mappings.keys())
            request = DescribeDBInstancePerformanceRequest.DescribeDBInstancePerformanceRequest()
            request.set_DBInstanceId(instance_id)
            request.set_Key(keys)
            request.set_StartTime(start_time.strftime("%Y-%m-%dT%H:%MZ"))
            request.set_EndTime(end_time.strftime("%Y-%m-%dT%H:%MZ"))
            response = client.do_action_with_exception(request)
            data = json.loads(response)
            latest_metrics = {}
            for perf_key in data.get("PerformanceKeys", {}).get("PerformanceKey", []):
                metric_name = perf_key.get("Key")
                values = perf_key.get("Values", {}).get("PerformanceValue", [])
                mappings = metric_mappings.get(metric_name, [])
                if values:
                    point = values[-1]
                    value_str = point.get("Value", "")
                    value_parts = value_str.split("&") if value_str else []
                    for smartdba_name, index, unit in mappings:
                        if index < len(value_parts):
                            try:
                                value = float(value_parts[index])
                                latest_metrics[smartdba_name] = {"datasource_id": ds["id"], "metric_name": smartdba_name, "metric_value": value, "labels": {"source": "aliyun_rds", "instance_id": instance_id, "unit": unit}}
                            except (ValueError, TypeError):
                                continue
            metrics.extend(latest_metrics.values())
            await context.log("info", "成功采集数据源 " + ds["name"] + " 的 " + str(len(latest_metrics)) + " 条指标")
        except Exception as e:
            await context.log("error", "采集数据源 " + ds["name"] + " 失败: " + str(e))
            raise ValueError("阿里云 API 调用失败: " + str(e))
    return metrics
"""
}

FEISHU_BOT_TEMPLATE = {
    "integration_id": "builtin_feishu_bot",
    "name": "飞书机器人对话",
    "description": "飞书机器人入站对话配置，用于数据库诊断会话",
    "integration_type": "bot",
    "category": "im",
    "config_schema": {"type": "object", "properties": {}, "required": []},
    "code": "APP_ID = \"\"\nAPP_SECRET = \"\"\nSIGNING_SECRET = \"\"\n\nasync def handle_event(context, params, payload):\n    return {\"success\": True, \"message\": \"Feishu bot is handled by dedicated router/service\"}\n"
}

WEIXIN_BOT_TEMPLATE = {
    "integration_id": "builtin_weixin_bot",
    "name": "微信机器人对话",
    "description": "微信机器人入站对话配置（OpenClaw 协议），通过长轮询收消息并回复",
    "integration_type": "bot",
    "category": "im",
    "config_schema": {"type": "object", "properties": {}, "required": []},
    "code": "async def handle_event(context, params, payload):\n    return {\"success\": True, \"message\": \"Weixin bot is handled by dedicated poller/service\"}\n"
}

BUILTIN_TEMPLATES = [
    FEISHU_WEBHOOK_TEMPLATE,
    FEISHU_BOT_TEMPLATE,
    WEIXIN_BOT_TEMPLATE,
    DINGTALK_WEBHOOK_TEMPLATE,
    EMAIL_TEMPLATE,
    GENERIC_WEBHOOK_TEMPLATE,
    ALIYUN_RDS_TEMPLATE
]
