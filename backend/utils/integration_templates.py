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
    "code": '''
import time
import hmac
import hashlib
import base64


async def send_notification(context, params, payload):
    webhook_url = params.get("webhook_url")
    secret = params.get("secret")

    is_recovery = payload.get("status") == "resolved"
    severity_colors = {
        "critical": "red",
        "high": "red",
        "warning": "orange",
        "medium": "orange",
        "low": "yellow",
        "info": "blue"
    }
    severity_labels = {
        "critical": "严重",
        "high": "高",
        "warning": "中",
        "medium": "中",
        "low": "低",
        "info": "提示"
    }
    color = "green" if is_recovery else severity_colors.get(payload.get("severity", ""), "blue")
    severity_label = severity_labels.get(payload.get("severity", ""), payload.get("severity", ""))

    elements = []

    alert_lines = [
        f"**告警类型：** {payload.get('alert_type', '未知')}",
        f"**严重程度：** {severity_label}",
    ]
    metric_name = payload.get("metric_name")
    metric_value = payload.get("metric_value")
    recovery_value = payload.get("resolved_value")
    if recovery_value is None:
        recovery_value = payload.get("recovery_value")
    threshold_value = payload.get("threshold_value")
    if metric_name:
        if is_recovery and recovery_value is not None:
            alert_lines.append(f"**恢复后值：** {metric_name} = {recovery_value:.2f}")
        elif metric_value is not None:
            alert_lines.append(f"**指标：** {metric_name} = {metric_value:.2f}")
        else:
            alert_lines.append(f"**指标：** {metric_name}")
    if threshold_value is not None:
        alert_lines.append(f"**阈值：** {threshold_value:.2f}")
    if payload.get("trigger_reason"):
        alert_lines.append(f"**触发原因：** {payload.get('trigger_reason')}")
    if is_recovery:
        if payload.get("created_at"):
            alert_lines.append(f"**告警时间：** {payload.get('created_at')}")
        if payload.get("resolved_at"):
            alert_lines.append(f"**恢复时间：** {payload.get('resolved_at')}")
    else:
        alert_lines.append(f"**触发时间：** {payload.get('timestamp', '')}")

    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\\n".join(alert_lines)}})

    ai_summary = payload.get("ai_diagnosis_summary")
    root_cause = payload.get("root_cause")
    recommended_actions = payload.get("recommended_actions")
    diagnosis_status = payload.get("diagnosis_status") or ""

    if ai_summary or root_cause or recommended_actions:
        elements.append({"tag": "hr"})
        diag_status_label = {"pending": "诊断中", "in_progress": "诊断中", "completed": "已完成", "failed": "失败"}.get(diagnosis_status, diagnosis_status or "")
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "**AI 诊断**" + (f"（{diag_status_label}）" if diag_status_label else "")}
        })
        if root_cause:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**&#x1F50D; 根本原因**\\n" + root_cause[:500]}})
        elif ai_summary:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**&#x1F4AC; 诊断摘要**\\n" + ai_summary[:300]}})
        if recommended_actions:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**&#x1F6E0; 处置建议**\\n" + recommended_actions[:500]}})

    actions = []
    if payload.get("alert_url"):
        actions.append({"tag": "button", "text": {"tag": "plain_text", "content": "查看告警详情"}, "type": "primary", "multi_url": {"url": payload["alert_url"], "pc_url": payload["alert_url"], "android_url": payload["alert_url"], "ios_url": payload["alert_url"]}})
    if payload.get("report_url"):
        actions.append({"tag": "button", "text": {"tag": "plain_text", "content": "查看诊断报告"}, "type": "default", "multi_url": {"url": payload["report_url"], "pc_url": payload["report_url"], "android_url": payload["report_url"], "ios_url": payload["report_url"]}})
    if actions:
        elements.append({"tag": "action", "actions": actions})

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": payload["title"]}, "template": color},
            "elements": elements
        }
    }

    headers = {"Content-Type": "application/json"}
    if secret:
        timestamp = str(int(time.time()))
        sign_string = timestamp + "\\n" + secret
        sign = base64.b64encode(hmac.new(sign_string.encode("utf-8"), digestmod=hashlib.sha256).digest()).decode("utf-8")
        card["timestamp"] = timestamp
        card["sign"] = sign

    response = await context.http_request("POST", webhook_url, json=card, headers=headers)
    if response.status_code == 200:
        return {"success": True, "message": "飞书通知发送成功"}
    else:
        return {"success": False, "message": "飞书通知发送失败: " + response.text}
'''
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
    "code": '''
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


async def send_notification(context, params, payload):
    smtp_host = await context.get_system_config("smtp_host")
    smtp_port = await context.get_system_config("smtp_port")
    smtp_username = await context.get_system_config("smtp_username")
    smtp_password = await context.get_system_config("smtp_password")
    smtp_from_email = await context.get_system_config("smtp_from_email")
    smtp_use_tls = await context.get_system_config("smtp_use_tls")

    if not all([smtp_host, smtp_port, smtp_username, smtp_password, smtp_from_email]):
        return {"success": False, "message": "SMTP 配置不完整，请在系统配置中设置"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = payload["title"]
    msg["From"] = smtp_from_email
    msg["To"] = params["to"]
    if params.get("cc"):
        msg["Cc"] = params["cc"]

    is_recovery = payload.get("status") == "resolved"
    severity_colors = {"critical": "#ff4d4f", "warning": "#faad14", "info": "#1890ff"}
    border_color = "#16a34a" if is_recovery else severity_colors.get(payload["severity"], "#1890ff")
    title_color = "#15803d" if is_recovery else border_color
    title_bg = "#f0fdf4" if is_recovery else "#fff1f0"
    content_html = payload["content"].replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>")

    metric_html = ""
    metric_name = payload.get("metric_name")
    recovery_value = payload.get("resolved_value")
    if recovery_value is None:
        recovery_value = payload.get("recovery_value")
    metric_value = payload.get("metric_value")
    if metric_name:
        if is_recovery and recovery_value is not None:
            metric_html = '<p style="margin:0 0 12px 0;font-size:15px;color:#111827;"><strong>恢复后值：</strong> ' + metric_name + ' = ' + format(recovery_value, '.2f') + '</p>'
        elif metric_value is not None:
            metric_html = '<p style="margin:0 0 12px 0;font-size:15px;color:#111827;"><strong>当前值：</strong> ' + metric_name + ' = ' + format(metric_value, '.2f') + '</p>'

    diagnosis_html = ""
    if payload.get("root_cause"):
        rc = payload["root_cause"].replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>")[:500]
        diagnosis_html += '<div style="margin-bottom:12px;padding:10px;background:#f0f7ff;border-left:3px solid #1890ff;border-radius:4px;"><p style="margin:0 0 4px 0;font-weight:bold;color:#1890ff;">&#x1F50D; 根本原因</p><p style="margin:0;color:#333;line-height:1.6;">' + rc + '</p></div>'
    if payload.get("recommended_actions"):
        ra = payload["recommended_actions"].replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>")[:500]
        diagnosis_html += '<div style="margin-bottom:12px;padding:10px;background:#f6ffed;border-left:3px solid #52c41a;border-radius:4px;"><p style="margin:0 0 4px 0;font-weight:bold;color:#52c41a;">&#x1F6E0; 处置建议</p><p style="margin:0;color:#333;line-height:1.6;">' + ra + '</p></div>'

    time_label = "恢复时间" if is_recovery else "触发时间"
    time_value = payload.get("resolved_at") or payload.get("timestamp")
    if not time_value:
        time_value = payload.get("created_at") or ""

    html = (
        '<html><body style="font-family:Arial,sans-serif;background:#f8fafc;margin:0;padding:16px;">'
        '<div style="max-width:880px;margin:0 auto;border:1px solid #dbe2ea;border-radius:16px;overflow:hidden;background:#ffffff;">'
        '<div style="padding:24px 28px;background:' + title_bg + ';border-bottom:1px solid #e5e7eb;">'
        '<div style="margin:0;font-size:18px;line-height:1.4;font-weight:700;color:' + title_color + ';">' + payload["title"] + '</div>'
        '</div>'
        '<div style="padding:28px;">'
        + metric_html +
        '<div style="font-size:15px;line-height:1.85;color:#111827;">' + content_html + '</div>'
        + diagnosis_html +
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">'
        '<p style="margin:0 0 8px 0;color:#111827;"><strong>数据源：</strong>' + payload["datasource_name"] + '</p>'
        '<p style="margin:0;color:#111827;"><strong>' + time_label + '：</strong>' + time_value + '</p>'
        '</div></div></body></html>'
    )

    msg.attach(MIMEText(html, "html"))

    def send_email_sync():
        server = None
        try:
            port = int(smtp_port)
            if port == 465 or smtp_use_tls == "ssl":
                server = smtplib.SMTP_SSL(smtp_host, port, timeout=20)
            else:
                server = smtplib.SMTP(smtp_host, port, timeout=20)
                if smtp_use_tls == "true":
                    server.starttls()
            server.login(smtp_username, smtp_password)
            recipients = [r.strip() for r in params["to"].split(",")]
            if params.get("cc"):
                recipients.extend([r.strip() for r in params["cc"].split(",")])
            server.sendmail(smtp_from_email, recipients, msg.as_string())
            return {"success": True, "message": "邮件发送成功"}
        except smtplib.SMTPAuthenticationError as e:
            return {"success": False, "message": "SMTP 认证失败: " + str(e)}
        except smtplib.SMTPConnectError as e:
            return {"success": False, "message": "无法连接 SMTP 服务器: " + str(e)}
        except TimeoutError:
            return {"success": False, "message": "连接 SMTP 服务器超时"}
        except Exception as e:
            return {"success": False, "message": "邮件发送失败: " + type(e).__name__ + ": " + str(e)}
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_thread_pool, send_email_sync)
    return result
'''
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
    "code": '''
async def send_notification(context, params, payload):
    webhook_url = params["webhook_url"]
    method = params.get("method", "POST")
    auth_type = params.get("auth_type", "none")
    auth_token = params.get("auth_token")

    headers = {"Content-Type": "application/json"}
    if auth_type == "bearer" and auth_token:
        headers["Authorization"] = "Bearer " + auth_token
    elif auth_type == "basic" and auth_token:
        headers["Authorization"] = "Basic " + auth_token

    webhook_payload = {
        "title": payload["title"],
        "content": payload["content"],
        "severity": payload["severity"],
        "status": payload.get("status"),
        "datasource_name": payload["datasource_name"],
        "alert_id": payload["alert_id"],
        "timestamp": payload["timestamp"],
        "created_at": payload.get("created_at"),
        "resolved_at": payload.get("resolved_at"),
        "metric_name": payload.get("metric_name"),
        "metric_value": payload.get("metric_value"),
        "resolved_value": payload.get("resolved_value"),
        "recovery_value": payload.get("recovery_value"),
        "threshold_value": payload.get("threshold_value"),
        "trigger_reason": payload.get("trigger_reason"),
        "ai_diagnosis_summary": payload.get("ai_diagnosis_summary"),
        "root_cause": payload.get("root_cause"),
        "recommended_actions": payload.get("recommended_actions"),
        "diagnosis_status": payload.get("diagnosis_status"),
        "alert_url": payload.get("alert_url"),
        "report_url": payload.get("report_url"),
    }

    response = await context.http_request(method, webhook_url, json=webhook_payload, headers=headers)
    if 200 <= response.status_code < 300:
        return {"success": True, "message": "Webhook 通知发送成功 (HTTP " + str(response.status_code) + ")"}
    else:
        return {"success": False, "message": "Webhook 通知发送失败: HTTP " + str(response.status_code) + ", " + response.text}
'''
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
    access_key_id = params.get("access_key_id") or await context.get_system_config("aliyun_access_key_id")
    access_key_secret = params.get("access_key_secret") or await context.get_system_config("aliyun_access_key_secret")
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云 AccessKey 未配置，请在系统配置中设置 aliyun_access_key_id 和 aliyun_access_key_secret")
    region_id = params.get("region_id", "cn-hangzhou")
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkrds.request.v20140815 import DescribeDBInstancePerformanceRequest, DescribeDBInstancesRequest
    except ImportError:
        raise ValueError("阿里云 SDK 未安装，请运行: pip install aliyun-python-sdk-core aliyun-python-sdk-rds")
    from datetime import datetime, timedelta
    import json

    db_type_aliases = {
        "mysql": "mysql",
        "mariadb": "mysql",
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "pgsql": "postgresql",
        "sqlserver": "sqlserver",
        "sql_server": "sqlserver",
        "mssql": "sqlserver",
    }

    engine_metric_configs = {
        "mysql": {
            "keys": [
                "MySQL_MemCpuUsage",
                "MySQL_RCU_MemCpuUsage",
                "MySQL_DetailedSpaceUsage",
                "MySQL_IOPS",
                "MySQL_MBPS",
                "MySQL_NetworkTraffic",
                "MySQL_QPSTPS",
                "MySQL_Sessions",
                "MySQL_ThreadStatus",
            ],
            "mappings": {
                "MySQL_MemCpuUsage": [
                    {"name": "cpu_usage", "index": 0, "unit": "%"},
                    {"name": "memory_usage", "index": 1, "unit": "%"},
                ],
                "MySQL_RCU_MemCpuUsage": [
                    {"name": "cpu_usage", "index": 0, "unit": "%"},
                    {"name": "memory_usage", "index": 1, "unit": "%"},
                ],
                "MySQL_DetailedSpaceUsage": [
                    {"name": "disk_total", "index": 0, "unit": "MB"},
                    {"name": "disk_data", "index": 1, "unit": "MB"},
                    {"name": "disk_log", "index": 2, "unit": "MB"},
                    {"name": "disk_temp", "index": 3, "unit": "MB"},
                    {"name": "disk_system", "index": 4, "unit": "MB"},
                ],
                "MySQL_IOPS": [
                    {"name": "iops", "index": 0, "unit": "次/秒"},
                ],
                "MySQL_MBPS": [
                    {"name": "throughput", "index": 0, "unit": "Byte/秒"},
                ],
                "MySQL_NetworkTraffic": [
                    {"name": "network_in", "index": 0, "unit": "KB/秒", "aliases": ["network_rx_bytes"]},
                    {"name": "network_out", "index": 1, "unit": "KB/秒", "aliases": ["network_tx_bytes"]},
                ],
                "MySQL_QPSTPS": [
                    {"name": "qps", "index": 0, "unit": "次/秒"},
                    {"name": "tps", "index": 1, "unit": "个/秒"},
                ],
                "MySQL_Sessions": [
                    {"name": "active_connections", "index": 0, "unit": "个", "aliases": ["connections_active"]},
                    {"name": "total_connections", "index": 1, "unit": "个", "aliases": ["connections_total"]},
                ],
                "MySQL_ThreadStatus": [
                    {"name": "active_connections", "index": 0, "unit": "个", "aliases": ["connections_active"]},
                    {"name": "total_connections", "index": 1, "unit": "个", "aliases": ["connections_total"]},
                ],
            },
        },
        "postgresql": {
            "keys": [
                "CpuUsage",
                "MemoryUsage",
                "PgSQL_SpaceUsage",
                "PgSQL_IOPS",
                "PgSQL_Session",
                "PolarDBConnections",
                "PolarDBQPSTPS",
            ],
            "mappings": {
                "CpuUsage": [
                    {"name": "cpu_usage", "index": 0, "unit": "%"},
                ],
                "MemoryUsage": [
                    {"name": "memory_usage", "index": 0, "unit": "%"},
                ],
                "PgSQL_SpaceUsage": [
                    {"name": "disk_total", "index": 0, "unit": "MB", "scale": 1.0 / (1024 * 1024)},
                ],
                "PgSQL_IOPS": [
                    {"name": "iops", "index": 0, "unit": "次/秒"},
                ],
                "PgSQL_Session": [
                    {"name": "total_connections", "index": 0, "unit": "个", "aliases": ["connections_total"]},
                ],
                "PolarDBConnections": [
                    {"name": "active_connections", "index": 0, "unit": "个", "aliases": ["connections_active"]},
                    {"name": "idle_connections", "index": 1, "unit": "个"},
                    {"name": "total_connections", "index": 2, "unit": "个", "aliases": ["connections_total"]},
                    {"name": "waiting_connections", "index": 3, "unit": "个"},
                ],
                "PolarDBQPSTPS": [
                    {"name": "commits_per_sec", "index": 0, "unit": "次/秒"},
                    {"name": "rollbacks_per_sec", "index": 1, "unit": "次/秒"},
                    {"name": "deadlocks_per_sec", "index": 2, "unit": "次/秒"},
                    {"name": "tps", "index": 3, "unit": "次/秒"},
                ],
            },
        },
        "sqlserver": {
            "keys": [
                "SQLServer_InstanceCPUUsage",
                "SQLServer_InstanceMemUsage",
                "SQLServer_InstanceDiskUsage",
                "SQLServer_DetailedSpaceUsage",
                "SQLServer_IOPS",
                "SQLServer_MBPS",
                "SQLServer_NetworkTraffic",
                "SQLServer_QPS",
                "SQLServer_Transactions",
                "SQLServer_Sessions",
                "SQLServer_BufferHit",
            ],
            "mappings": {
                "SQLServer_InstanceCPUUsage": [
                    {"name": "cpu_usage", "index": 0, "unit": "%"},
                ],
                "SQLServer_InstanceMemUsage": [
                    {"name": "memory_usage", "index": 0, "unit": "%"},
                ],
                "SQLServer_InstanceDiskUsage": [
                    {"name": "disk_usage", "index": 0, "unit": "%"},
                ],
                "SQLServer_DetailedSpaceUsage": [
                    {"name": "disk_total", "index": 0, "unit": "MB"},
                    {"name": "disk_data", "index": 1, "unit": "MB"},
                    {"name": "disk_log", "index": 2, "unit": "MB"},
                    {"name": "disk_system", "index": 3, "unit": "MB"},
                    {"name": "disk_temp", "index": 4, "unit": "MB"},
                ],
                "SQLServer_IOPS": [
                    {"name": "iops", "index": 0, "unit": "次/秒"},
                    {"name": "disk_reads_per_sec", "index": 1, "unit": "次/秒"},
                    {"name": "disk_writes_per_sec", "index": 2, "unit": "次/秒"},
                ],
                "SQLServer_MBPS": [
                    {"name": "throughput", "index": 0, "unit": "Byte/秒"},
                ],
                "SQLServer_NetworkTraffic": [
                    {"name": "network_out", "index": 0, "unit": "KB/秒", "aliases": ["network_tx_bytes"]},
                    {"name": "network_in", "index": 1, "unit": "KB/秒", "aliases": ["network_rx_bytes"]},
                ],
                "SQLServer_QPS": [
                    {"name": "qps", "index": 0, "unit": "次/秒"},
                ],
                "SQLServer_Transactions": [
                    {"name": "tps", "index": 0, "unit": "次/秒"},
                    {"name": "write_transactions_per_sec", "index": 1, "unit": "次/秒"},
                ],
                "SQLServer_Sessions": [
                    {"name": "active_transactions", "index": 1, "unit": "个"},
                    {"name": "active_cursors", "index": 2, "unit": "个"},
                    {"name": "active_connections", "index": 3, "unit": "个", "aliases": ["connections_active"]},
                    {"name": "total_connections", "index": 5, "unit": "个", "aliases": ["connections_total"]},
                ],
                "SQLServer_BufferHit": [
                    {"name": "cache_hit_rate", "index": 0, "unit": "%", "aliases": ["buffer_pool_hit_rate"]},
                ],
            },
        },
    }

    def ensure_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def normalize_db_type(db_type):
        key = (db_type or "").strip().lower()
        return db_type_aliases.get(key, key)

    def build_metric_point(datasource_id, instance_id, metric_name, metric_value, unit, timestamp=None):
        point = {
            "datasource_id": datasource_id,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "labels": {
                "source": "aliyun_rds",
                "instance_id": instance_id,
                "unit": unit,
            }
        }
        if timestamp:
            point["timestamp"] = timestamp
        return point

    def convert_value(raw_value, scale=1.0):
        try:
            return round(float(raw_value) * float(scale), 4)
        except (TypeError, ValueError):
            return None

    def validate_credentials(client):
        request = DescribeDBInstancesRequest.DescribeDBInstancesRequest()
        if hasattr(request, "set_PageSize"):
            request.set_PageSize(1)
        client.do_action_with_exception(request)

    client = AcsClient(access_key_id, access_key_secret, region_id)
    try:
        validate_credentials(client)
    except Exception as e:
        raise ValueError("阿里云 AccessKey 验证失败，请检查配置: " + str(e))

    metrics = []
    if not datasources:
        await context.log("info", "没有配置数据源，阿里云凭证验证已通过")
        return metrics

    for ds in datasources:
        db_type = normalize_db_type(ds.get("db_type"))
        if db_type not in engine_metric_configs:
            raise ValueError("数据源 " + ds["name"] + " 的数据库类型暂不支持阿里云 RDS 外部采集: " + str(ds.get("db_type")))
        instance_id = ds.get("external_instance_id")
        if not instance_id:
            raise ValueError("数据源 " + ds["name"] + " 未配置 external_instance_id")
        try:
            config = engine_metric_configs[db_type]
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            keys = ",".join(config["keys"])
            request = DescribeDBInstancePerformanceRequest.DescribeDBInstancePerformanceRequest()
            request.set_DBInstanceId(instance_id)
            request.set_Key(keys)
            request.set_StartTime(start_time.strftime("%Y-%m-%dT%H:%MZ"))
            request.set_EndTime(end_time.strftime("%Y-%m-%dT%H:%MZ"))
            response = client.do_action_with_exception(request)
            data = json.loads(response)
            latest_metrics = {}
            performance_keys = ensure_list(data.get("PerformanceKeys", {}).get("PerformanceKey"))
            for perf_key in performance_keys:
                metric_name = perf_key.get("Key")
                values = ensure_list(perf_key.get("Values", {}).get("PerformanceValue"))
                mappings = config["mappings"].get(metric_name, [])
                if not values or not mappings:
                    continue
                point = values[-1]
                timestamp = point.get("Date") or point.get("DateTime") or point.get("Timestamp")
                value_str = point.get("Value", "")
                value_parts = value_str.split("&") if value_str else []
                for mapping in mappings:
                    index = mapping.get("index", 0)
                    if index >= len(value_parts):
                        continue
                    value = convert_value(value_parts[index], mapping.get("scale", 1.0))
                    if value is None:
                        continue
                    metric = build_metric_point(ds["id"], instance_id, mapping["name"], value, mapping["unit"], timestamp)
                    latest_metrics[metric["metric_name"]] = metric
                    for alias in mapping.get("aliases", []):
                        latest_metrics[alias] = build_metric_point(ds["id"], instance_id, alias, value, mapping["unit"], timestamp)
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
