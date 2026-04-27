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
    is_ai_policy = payload.get("alert_type") == "ai_policy_violation"
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

    def _safe_md(text):
        return str(text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n").strip()

    elements = []

    alert_lines = [
        f"**告警类型：** {payload.get('alert_type', '未知')}",
        f"**严重程度：** {severity_label}",
    ]
    native_metric_summary = _safe_md(payload.get("native_metric_summary"))
    metric_name = payload.get("metric_name")
    metric_value = payload.get("metric_value")
    recovery_value = payload.get("resolved_value")
    if recovery_value is None:
        recovery_value = payload.get("recovery_value")
    threshold_value = payload.get("threshold_value")
    if native_metric_summary:
        alert_lines.append(f"**指标：**\\n{native_metric_summary}")
    elif metric_name and not (is_ai_policy and metric_value is None):
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
    ai_summary_markdown = _safe_md(payload.get("ai_diagnosis_summary_markdown") or ai_summary)
    root_cause_markdown = _safe_md(payload.get("root_cause_markdown") or root_cause)
    recommended_actions_markdown = _safe_md(payload.get("recommended_actions_markdown") or recommended_actions)
    diagnosis_status = payload.get("diagnosis_status") or ""

    if ai_summary or root_cause or recommended_actions:
        elements.append({"tag": "hr"})
        diag_status_label = {"pending": "诊断中", "in_progress": "诊断中", "completed": "已完成", "failed": "失败"}.get(diagnosis_status, diagnosis_status or "")
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "**AI 诊断**" + (f"（{diag_status_label}）" if diag_status_label else "")}
        })
        if root_cause_markdown:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**&#x1F50D; 根本原因**\\n" + root_cause_markdown[:800]}})
        elif ai_summary_markdown:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**&#x1F4AC; 诊断摘要**\\n" + ai_summary_markdown[:500]}})
        if recommended_actions_markdown:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**&#x1F6E0; 处置建议**\\n" + recommended_actions_markdown[:800]}})

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
                except Exception:
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
async def fetch_metrics(context, params, datasource):
    access_key_id = params.get("access_key_id") or await context.get_system_config("aliyun_access_key_id")
    access_key_secret = params.get("access_key_secret") or await context.get_system_config("aliyun_access_key_secret")
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云 AccessKey 未配置，请在系统配置中设置 aliyun_access_key_id 和 aliyun_access_key_secret")
    region_id = params.get("region_id", "cn-hangzhou")
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkrds.request.v20140815 import (
            DescribeDBInstanceAttributeRequest,
            DescribeDBInstancePerformanceRequest,
            DescribeDBInstancesRequest,
        )
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
                    {"name": "disk_used", "index": 0, "unit": "MB"},
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
                    {"name": "connections_active", "index": 0, "unit": "个"},
                    {"name": "connections_total", "index": 1, "unit": "个"},
                ],
                "MySQL_ThreadStatus": [
                    {"name": "threads_running", "index": 0, "unit": "个"},
                    {"name": "threads_connected", "index": 1, "unit": "个"},
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
                    {"name": "disk_used", "index": 0, "unit": "MB", "scale": 1.0 / (1024 * 1024)},
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
                    {"name": "disk_used", "index": 0, "unit": "MB"},
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

    def get_first_item(value):
        if isinstance(value, list):
            return value[0] if value else {}
        if isinstance(value, dict):
            return value
        return {}

    def build_attribute_metrics(datasource_id, instance_id, attribute_data):
        items = attribute_data.get("Items", {}) if isinstance(attribute_data, dict) else {}
        attribute = get_first_item(items.get("DBInstanceAttribute"))
        if not attribute:
            return {}

        metrics_map = {}
        storage_gb = convert_value(attribute.get("DBInstanceStorage"))
        disk_used_bytes = convert_value(attribute.get("DBInstanceDiskUsed"))

        if storage_gb is not None and storage_gb > 0:
            storage_mb = round(storage_gb * 1024, 4)
            metrics_map["disk_total"] = build_metric_point(datasource_id, instance_id, "disk_total", storage_mb, "MB")

        if disk_used_bytes is not None and disk_used_bytes >= 0:
            disk_used_mb = round(disk_used_bytes / (1024 * 1024), 4)
            metrics_map["disk_used"] = build_metric_point(datasource_id, instance_id, "disk_used", disk_used_mb, "MB")

        if (
            storage_gb is not None and storage_gb > 0
            and disk_used_bytes is not None and disk_used_bytes >= 0
        ):
            total_bytes = storage_gb * 1024 * 1024 * 1024
            if total_bytes > 0:
                disk_usage = round((disk_used_bytes / total_bytes) * 100, 4)
                metrics_map["disk_usage"] = build_metric_point(datasource_id, instance_id, "disk_usage", disk_usage, "%")

        return metrics_map

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
    if not datasource:
        await context.log("info", "没有配置数据源，阿里云凭证验证已通过")
        return metrics

    for ds in datasource:
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
            latest_metric_priority = {}
            metric_source_priority = {
                "MySQL_MemCpuUsage": 20,
                "MySQL_RCU_MemCpuUsage": 10,
            }
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
                    priority = metric_source_priority.get(metric_name, 0)
                    existing_priority = latest_metric_priority.get(metric["metric_name"], -1)
                    if priority < existing_priority:
                        continue
                    latest_metrics[metric["metric_name"]] = metric
                    latest_metric_priority[metric["metric_name"]] = priority
                    for alias in mapping.get("aliases", []):
                        if priority < latest_metric_priority.get(alias, -1):
                            continue
                        latest_metrics[alias] = build_metric_point(ds["id"], instance_id, alias, value, mapping["unit"], timestamp)
                        latest_metric_priority[alias] = priority

            attribute_request = DescribeDBInstanceAttributeRequest.DescribeDBInstanceAttributeRequest()
            attribute_request.set_DBInstanceId(instance_id)
            attribute_response = client.do_action_with_exception(attribute_request)
            attribute_metrics = build_attribute_metrics(ds["id"], instance_id, json.loads(attribute_response))
            latest_metrics.update(attribute_metrics)

            metrics.extend(latest_metrics.values())
            await context.log("info", "成功采集数据源 " + ds["name"] + " 的 " + str(len(latest_metrics)) + " 条指标")
        except Exception as e:
            await context.log("error", "采集数据源 " + ds["name"] + " 失败: " + str(e))
            raise ValueError("阿里云 API 调用失败: " + str(e))
    return metrics
"""
}

# 华为云 RDS 监控数据采集模板
HUAWEI_CLOUD_RDS_TEMPLATE = {
    "integration_id": "builtin_huaweicloud_rds",
    "name": "华为云 RDS 监控数据采集",
    "description": "从华为云 CES API 采集 RDS 监控指标，需要在数据源上填写实例 ID；AK/SK 从系统参数读取",
    "integration_type": "inbound_metric",
    "category": "monitoring",
    "config_schema": {
        "type": "object",
        "properties": {
            "region_id": {
                "type": "string",
                "title": "区域 ID",
                "default": "cn-north-4",
                "description": "华为云区域 ID，例如 cn-north-4、cn-east-3。CES/IAM 端点依赖 region_id，不能仅靠实例 ID 自动推断"
            },
            "project_id": {
                "type": "string",
                "title": "项目 ID（可选）",
                "description": "留空时会自动按 region_id 查找对应项目 ID"
            }
        },
        "required": ["region_id"]
    },
    "code": """
async def fetch_metrics(context, params, datasource):
    from datetime import datetime, timedelta, timezone
    import hashlib
    import hmac
    import json
    from urllib.parse import quote, urlsplit

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
            "dimension_candidates": ["rds_cluster_id"],
            "metric_names": [
                "rds001_cpu_util",
                "rds002_mem_util",
                "rds003_iops",
                "rds004_bytes_in",
                "rds005_bytes_out",
                "rds006_conn_count",
                "rds007_conn_active_count",
                "rds008_qps",
                "rds009_tps",
                "rds011_innodb_buf_hit",
                "rds015_innodb_read_count",
                "rds016_innodb_write_count",
                "rds039_disk_util",
                "rds047_disk_total_size",
                "rds048_disk_used_size",
                "rds049_disk_read_throughput",
                "rds050_disk_write_throughput",
            ],
            "mappings": {
                "rds001_cpu_util": {"name": "cpu_usage", "unit": "%"},
                "rds002_mem_util": {"name": "memory_usage", "unit": "%"},
                "rds003_iops": {"name": "iops", "unit": "count/s"},
                # 华为云该指标返回 Bytes/s，这里统一归一化为系统内部使用的 KB/s
                "rds004_bytes_in": {"name": "network_in", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_rx_bytes"]},
                "rds005_bytes_out": {"name": "network_out", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_tx_bytes"]},
                "rds006_conn_count": {"name": "connections_total", "unit": "count", "aliases": ["total_connections"]},
                "rds007_conn_active_count": {"name": "connections_active", "unit": "count", "aliases": ["active_connections"]},
                "rds008_qps": {"name": "qps", "unit": "count/s"},
                "rds009_tps": {"name": "tps", "unit": "count/s"},
                "rds011_innodb_buf_hit": {"name": "buffer_pool_hit_rate", "unit": "ratio", "aliases": ["cache_hit_rate"]},
                "rds015_innodb_read_count": {"name": "disk_reads_per_sec", "unit": "count/s"},
                "rds016_innodb_write_count": {"name": "disk_writes_per_sec", "unit": "count/s"},
                "rds039_disk_util": {"name": "disk_usage", "unit": "%"},
                "rds047_disk_total_size": {"name": "disk_total", "unit": "GiB"},
                "rds048_disk_used_size": {"name": "disk_used", "unit": "GiB"},
                "rds049_disk_read_throughput": {"name": "disk_read_bytes_per_sec", "unit": "KiB/s"},
                "rds050_disk_write_throughput": {"name": "disk_write_bytes_per_sec", "unit": "KiB/s"},
            },
        },
        "postgresql": {
            "dimension_candidates": ["postgresql_cluster_id", "rds_cluster_id"],
            "metric_names": [
                "rds001_cpu_util",
                "rds002_mem_util",
                "rds003_iops",
                "rds004_bytes_in",
                "rds005_bytes_out",
                "rds039_disk_util",
                "rds042_database_connections",
                "rds047_disk_total_size",
                "rds048_disk_used_size",
                "rds049_disk_read_throughput",
                "rds050_disk_write_throughput",
                "read_count_per_second",
                "write_count_per_second",
                "active_connections",
                "rds082_tps",
            ],
            "mappings": {
                "rds001_cpu_util": {"name": "cpu_usage", "unit": "%"},
                "rds002_mem_util": {"name": "memory_usage", "unit": "%"},
                "rds003_iops": {"name": "iops", "unit": "count/s"},
                # 华为云该指标返回 Bytes/s，这里统一归一化为系统内部使用的 KB/s
                "rds004_bytes_in": {"name": "network_in", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_rx_bytes"]},
                "rds005_bytes_out": {"name": "network_out", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_tx_bytes"]},
                "rds039_disk_util": {"name": "disk_usage", "unit": "%"},
                "rds042_database_connections": {"name": "connections_total", "unit": "count", "aliases": ["total_connections"]},
                "rds047_disk_total_size": {"name": "disk_total", "unit": "GiB"},
                "rds048_disk_used_size": {"name": "disk_used", "unit": "GiB"},
                "rds049_disk_read_throughput": {"name": "disk_read_bytes_per_sec", "unit": "KiB/s"},
                "rds050_disk_write_throughput": {"name": "disk_write_bytes_per_sec", "unit": "KiB/s"},
                "read_count_per_second": {"name": "disk_reads_per_sec", "unit": "count/s"},
                "write_count_per_second": {"name": "disk_writes_per_sec", "unit": "count/s"},
                "active_connections": {"name": "active_connections", "unit": "count", "aliases": ["connections_active"]},
                "rds082_tps": {"name": "tps", "unit": "count/s"},
            },
        },
        "sqlserver": {
            "dimension_candidates": ["rds_cluster_sqlserver_id", "rds_cluster_id"],
            "metric_names": [
                "rds001_cpu_util",
                "rds002_mem_util",
                "rds003_iops",
                "rds004_bytes_in",
                "rds005_bytes_out",
                "rds039_disk_util",
                "rds047_disk_total_size",
                "rds048_disk_used_size",
                "rds049_disk_read_throughput",
                "rds050_disk_write_throughput",
                "rds054_db_connections_in_use",
                "rds055_transactions_per_sec",
                "rds056_batch_per_sec",
                "rds059_cache_hit_ratio",
            ],
            "mappings": {
                "rds001_cpu_util": {"name": "cpu_usage", "unit": "%"},
                "rds002_mem_util": {"name": "memory_usage", "unit": "%"},
                "rds003_iops": {"name": "iops", "unit": "count/s"},
                # 华为云该指标返回 Bytes/s，这里统一归一化为系统内部使用的 KB/s
                "rds004_bytes_in": {"name": "network_in", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_rx_bytes"]},
                "rds005_bytes_out": {"name": "network_out", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_tx_bytes"]},
                "rds039_disk_util": {"name": "disk_usage", "unit": "%"},
                "rds047_disk_total_size": {"name": "disk_total", "unit": "GiB"},
                "rds048_disk_used_size": {"name": "disk_used", "unit": "GiB"},
                "rds049_disk_read_throughput": {"name": "disk_read_bytes_per_sec", "unit": "KiB/s"},
                "rds050_disk_write_throughput": {"name": "disk_write_bytes_per_sec", "unit": "KiB/s"},
                "rds054_db_connections_in_use": {"name": "active_connections", "unit": "count", "aliases": ["connections_active"]},
                "rds055_transactions_per_sec": {"name": "tps", "unit": "count/s"},
                "rds056_batch_per_sec": {"name": "qps", "unit": "count/s", "aliases": ["batch_requests_per_sec"]},
                "rds059_cache_hit_ratio": {"name": "cache_hit_rate", "unit": "%", "aliases": ["buffer_pool_hit_rate"]},
            },
        },
    }

    def normalize_db_type(db_type):
        key = (db_type or "").strip().lower()
        return db_type_aliases.get(key, key)

    async def get_config_value(param_key, system_key, default=None):
        value = params.get(param_key)
        if value not in (None, ""):
            return value
        if system_key:
            config_value = await context.get_system_config(system_key)
            if config_value not in (None, ""):
                return config_value
        return default

    def normalize_endpoint(endpoint):
        endpoint = (endpoint or "").strip()
        if not endpoint:
            return ""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint.rstrip("/")
        return ("https://" + endpoint).rstrip("/")

    def build_endpoint(service_name, region_id, custom_endpoint=None):
        if custom_endpoint:
            return normalize_endpoint(custom_endpoint)
        return "https://" + service_name + "." + region_id + ".myhuaweicloud.com"

    def json_dumps(payload):
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def sha256_hex(content):
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content or b"").hexdigest()

    def build_canonical_uri(path):
        path = path or "/"
        encoded = "/".join(quote(segment, safe="-_.~") for segment in path.split("/"))
        if not encoded.startswith("/"):
            encoded = "/" + encoded
        if not encoded.endswith("/"):
            encoded += "/"
        return encoded

    def build_canonical_query(query):
        if not query:
            return ""
        pairs = []
        for part in query.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
            else:
                key, value = part, ""
            pairs.append((
                quote(key, safe="-_.~"),
                quote(value, safe="-_.~"),
            ))
        pairs.sort()
        return "&".join(key + "=" + value for key, value in pairs)

    def build_canonical_headers(headers):
        canonical_lines = []
        header_names = []
        for name in sorted(headers):
            normalized_name = name.strip().lower()
            normalized_value = " ".join(str(headers[name]).strip().split())
            canonical_lines.append(normalized_name + ":" + normalized_value)
            header_names.append(normalized_name)
        return "\\n".join(canonical_lines) + "\\n", ";".join(header_names)

    def build_signed_headers(method, url, body_text="", extra_headers=None):
        parsed = urlsplit(url)
        host = parsed.netloc
        sdk_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        headers_to_sign = {
            "content-type": "application/json",
            "host": host,
            "x-sdk-date": sdk_date,
        }
        for key, value in (extra_headers or {}).items():
            if value not in (None, ""):
                headers_to_sign[key] = value

        canonical_headers, signed_headers = build_canonical_headers(headers_to_sign)
        canonical_request = "\\n".join([
            method.upper(),
            build_canonical_uri(parsed.path),
            build_canonical_query(parsed.query),
            canonical_headers,
            signed_headers,
            sha256_hex(body_text),
        ])
        string_to_sign = "\\n".join([
            "SDK-HMAC-SHA256",
            sdk_date,
            sha256_hex(canonical_request),
        ])
        signature = hmac.new(
            access_key_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        request_headers = {
            "Content-Type": "application/json",
            "Host": host,
            "X-Sdk-Date": sdk_date,
            "Authorization": (
                "SDK-HMAC-SHA256 "
                + "Access="
                + access_key_id
                + ", SignedHeaders="
                + signed_headers
                + ", Signature="
                + signature
            ),
        }
        for key, value in (extra_headers or {}).items():
            if value not in (None, ""):
                request_headers[key] = value
        return request_headers

    async def signed_request(method, url, payload=None, extra_headers=None):
        body_text = ""
        kwargs = {}
        if payload is not None:
            body_text = json_dumps(payload)
            kwargs["data"] = body_text
        kwargs["headers"] = build_signed_headers(method, url, body_text, extra_headers=extra_headers)
        return await context.http_request(method, url, **kwargs)

    def to_float(value, scale=1.0):
        try:
            return round(float(value) * float(scale), 4)
        except (TypeError, ValueError):
            return None

    def to_iso_timestamp(timestamp_ms):
        try:
            dt = datetime.fromtimestamp(float(timestamp_ms) / 1000.0, tz=timezone.utc)
            return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except Exception:
            return None

    def build_metric_point(datasource_id, instance_id, metric_name, metric_value, unit, timestamp=None):
        point = {
            "datasource_id": datasource_id,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "labels": {
                "source": "huaweicloud_rds",
                "instance_id": instance_id,
                "region_id": region_id,
                "unit": unit,
            }
        }
        if timestamp:
            point["timestamp"] = timestamp
        return point

    def append_metric(target, datasource_id, instance_id, metric_name, metric_value, unit, timestamp=None, aliases=None):
        target[metric_name] = build_metric_point(datasource_id, instance_id, metric_name, metric_value, unit, timestamp)
        for alias in aliases or []:
            target[alias] = build_metric_point(datasource_id, instance_id, alias, metric_value, unit, timestamp)

    def build_batch_request(metric_names, dimension_name, instance_id, start_ms, end_ms):
        return {
            "from": start_ms,
            "to": end_ms,
            "period": "300",
            "filter": "average",
            "metrics": [
                {
                    "namespace": "SYS.RDS",
                    "metric_name": metric_name,
                    "dimensions": [{"name": dimension_name, "value": instance_id}],
                }
                for metric_name in metric_names
            ]
        }

    def extract_response_metrics(payload):
        if not isinstance(payload, dict):
            return []
        metrics = payload.get("metrics")
        if isinstance(metrics, list):
            return metrics
        return []

    def pick_latest_datapoint(datapoints):
        latest = None
        latest_ts = -1
        for datapoint in datapoints or []:
            timestamp = datapoint.get("timestamp")
            try:
                current_ts = float(timestamp)
            except (TypeError, ValueError):
                current_ts = -1
            if latest is None or current_ts >= latest_ts:
                latest = datapoint
                latest_ts = current_ts
        return latest

    def extract_datapoint_value(datapoint):
        if not isinstance(datapoint, dict):
            return None
        for key in ("average", "max", "min", "sum"):
            value = datapoint.get(key)
            if value is not None:
                return value
        return None

    region_id = params.get("region_id", "cn-north-4")
    project_id = await get_config_value("project_id", None)
    project_name = await get_config_value("project_name", "huaweicloud_project_name", region_id) or region_id
    access_key_id = await context.get_system_config("huaweicloud_access_key_id")
    access_key_secret = await context.get_system_config("huaweicloud_access_key_secret")
    domain_name = await context.get_system_config("huaweicloud_domain_name")
    iam_username = await context.get_system_config("huaweicloud_iam_username")
    iam_password = await context.get_system_config("huaweicloud_iam_password")
    iam_endpoint = build_endpoint("iam", region_id, params.get("iam_endpoint"))
    ces_endpoint = build_endpoint("ces", region_id, params.get("ces_endpoint"))
    rds_endpoint = build_endpoint("rds", region_id, params.get("rds_endpoint"))

    request_json = None

    if access_key_id and access_key_secret:
        if not project_id:
            project_response = await signed_request("GET", iam_endpoint + "/v3/projects")
            if project_response.status_code != 200:
                raise ValueError(
                    "华为云 IAM 项目查询失败: HTTP "
                    + str(project_response.status_code)
                    + ", "
                    + project_response.text
                )

            projects = (project_response.json() or {}).get("projects") or []
            matched_project = next(
                (
                    item
                    for item in projects
                    if item.get("name") == project_name
                    or item.get("name") == region_id
                ),
                None,
            )
            project_id = (matched_project or {}).get("id")
            if not project_id:
                raise ValueError(
                    "未找到华为云项目 ID，请确认 region_id="
                    + str(region_id)
                    + " 对应的项目可访问，或手动填写 project_id"
                )
        elif not datasource:
            project_response = await signed_request("GET", iam_endpoint + "/v3/projects")
            if project_response.status_code != 200:
                raise ValueError(
                    "华为云 AK/SK 鉴权失败: HTTP "
                    + str(project_response.status_code)
                    + ", "
                    + project_response.text
                )

        async def request_json(method, url, payload=None):
            return await signed_request(method, url, payload=payload)

    elif domain_name and iam_username and iam_password:
        token_body = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": iam_username,
                            "password": iam_password,
                            "domain": {"name": domain_name},
                        }
                    },
                },
                "scope": {
                    "project": {"name": project_name}
                },
            }
        }

        token_response = await context.http_request(
            "POST",
            iam_endpoint + "/v3/auth/tokens",
            json=token_body,
            headers={"Content-Type": "application/json"},
        )
        if token_response.status_code not in (200, 201):
            raise ValueError(
                "华为云 IAM 鉴权失败: HTTP "
                + str(token_response.status_code)
                + ", "
                + token_response.text
            )

        subject_token = token_response.header("X-Subject-Token") or token_response.header("x-subject-token")
        if not subject_token:
            raise ValueError("华为云 IAM 鉴权成功，但响应头缺少 X-Subject-Token")

        token_payload = token_response.json() or {}
        project = ((token_payload.get("token") or {}).get("project") or {})
        project_id = project.get("id")
        if not project_id:
            raise ValueError("华为云 IAM 鉴权成功，但响应中未返回 project.id")

        async def request_json(method, url, payload=None):
            kwargs = {
                "headers": {
                    "Content-Type": "application/json",
                    "X-Auth-Token": subject_token,
                }
            }
            if payload is not None:
                kwargs["json"] = payload
            return await context.http_request(method, url, **kwargs)

    else:
        raise ValueError(
            "华为云凭据未配置，请先在系统参数中设置 "
            "huaweicloud_access_key_id / huaweicloud_access_key_secret"
        )

    metrics = []
    if not datasource:
        await context.log("info", "没有配置数据源，华为云凭证验证已通过")
        return metrics

    async def get_rds_instance(instance_id):
        response = await request_json(
            "GET",
            rds_endpoint + "/v3/" + project_id + "/instances?id=" + quote(str(instance_id), safe="") + "&limit=1"
        )
        if response.status_code != 200:
            raise ValueError(
                "华为云 RDS 实例查询失败: HTTP "
                + str(response.status_code)
                + ", "
                + response.text
            )
        payload = response.json() or {}
        instances = payload.get("instances") or []
        return instances[0] if instances else None

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    query_url = ces_endpoint + "/V1.0/" + project_id + "/batch-query-metric-data"

    for ds in datasource:
        db_type = normalize_db_type(ds.get("db_type"))
        if db_type not in engine_metric_configs:
            raise ValueError("数据源 " + ds["name"] + " 的数据库类型暂不支持华为云 RDS 外部采集: " + str(ds.get("db_type")))

        instance_id = ds.get("external_instance_id")
        if not instance_id:
            raise ValueError("数据源 " + ds["name"] + " 未配置 external_instance_id")

        rds_instance = await get_rds_instance(instance_id)
        if not rds_instance:
            raise ValueError(
                "华为云 RDS API 未找到实例 "
                + str(instance_id)
                + "。请核对该数据源的 external_instance_id、region_id，"
                + "并确认当前系统参数中的 AK/SK 属于该实例所在账号/项目"
            )

        config = engine_metric_configs[db_type]
        response_metrics = None
        used_dimension = None
        last_error = None

        for dimension_name in config["dimension_candidates"]:
            request_body = build_batch_request(config["metric_names"], dimension_name, instance_id, start_ms, end_ms)
            response = await request_json("POST", query_url, request_body)
            if response.status_code != 200:
                last_error = "HTTP " + str(response.status_code) + ", " + response.text
                continue

            current_metrics = extract_response_metrics(response.json())
            if response_metrics is None:
                response_metrics = current_metrics
                used_dimension = dimension_name
            if any(metric.get("datapoints") for metric in current_metrics):
                response_metrics = current_metrics
                used_dimension = dimension_name
                break

        if response_metrics is None:
            raise ValueError("华为云 CES 调用失败: " + (last_error or "未返回有效响应"))

        latest_metrics = {}
        latest_metric_timestamps = {}

        for remote_metric in response_metrics:
            remote_metric_name = remote_metric.get("metric_name")
            mapping = config["mappings"].get(remote_metric_name)
            if not mapping:
                continue

            datapoint = pick_latest_datapoint(remote_metric.get("datapoints") or [])
            if not datapoint:
                continue

            raw_value = extract_datapoint_value(datapoint)
            value = to_float(raw_value, mapping.get("scale", 1.0))
            if value is None:
                continue

            timestamp_ms = datapoint.get("timestamp")
            timestamp = to_iso_timestamp(timestamp_ms)
            try:
                metric_timestamp = float(timestamp_ms)
            except (TypeError, ValueError):
                metric_timestamp = -1

            metric_names = [mapping["name"]] + list(mapping.get("aliases", []))
            existing_timestamp = max([latest_metric_timestamps.get(name, -1) for name in metric_names] or [-1])
            if metric_timestamp < existing_timestamp:
                continue

            append_metric(
                latest_metrics,
                ds["id"],
                instance_id,
                mapping["name"],
                value,
                mapping["unit"],
                timestamp,
                mapping.get("aliases"),
            )
            for metric_name in metric_names:
                latest_metric_timestamps[metric_name] = metric_timestamp

        if not latest_metrics:
            raise ValueError(
                "华为云 CES 未返回实例 "
                + str(instance_id)
                + " 的监控数据。已尝试维度 "
                + ",".join(config["dimension_candidates"])
                + "；请核对实例 ID、region_id，或确认当前 AK/SK 是否有该实例监控查看权限"
            )

        metrics.extend(latest_metrics.values())
        await context.log(
            "info",
            "成功采集数据源 " + ds["name"] + " 的 " + str(len(latest_metrics)) + " 条指标（维度 " + str(used_dimension) + "）"
        )

    return metrics
"""
}

# 腾讯云 RDS / TDSQL-C 监控数据采集模板
TENCENT_CLOUD_RDS_TEMPLATE = {
    "integration_id": "builtin_tencentcloud_rds",
    "name": "腾讯云 RDS 监控数据采集",
    "description": "从腾讯云可观测平台采集 MySQL、PostgreSQL、SQL Server、TDSQL-C MySQL 监控指标，SecretId/SecretKey 从系统参数读取，需要在数据源上填写实例 ID",
    "integration_type": "inbound_metric",
    "category": "monitoring",
    "config_schema": {
        "type": "object",
        "properties": {
            "region_id": {
                "type": "string",
                "title": "地域",
                "default": "ap-guangzhou",
                "description": "腾讯云地域，例如 ap-guangzhou、ap-shanghai。SQL Server 监控维度和公共请求头都依赖该值"
            },
            "mysql_instance_type": {
                "type": "string",
                "title": "MySQL 实例类型（可选）",
                "default": "1",
                "description": "仅 MySQL 使用，默认 1 表示主实例；只读实例可填写 3，代理节点可填写 proxy"
            }
        },
        "required": ["region_id"]
    },
    "code": """
async def fetch_metrics(context, params, datasource):
    import hashlib
    import hmac
    import json
    import time
    from datetime import datetime, timedelta, timezone

    secret_id = str(params.get("secret_id") or await context.get_system_config("tencentcloud_secret_id") or "").strip()
    secret_key = str(params.get("secret_key") or await context.get_system_config("tencentcloud_secret_key") or "").strip()
    region_input = str(params.get("region_id") or "ap-guangzhou").strip()
    mysql_instance_type = str(params.get("mysql_instance_type") or "1").strip()
    endpoint = "monitor.tencentcloudapi.com"
    service = "monitor"
    version = "2018-07-24"

    if not secret_id or not secret_key:
        raise ValueError("腾讯云 SecretId/SecretKey 未配置，请在系统参数中设置 tencentcloud_secret_id 和 tencentcloud_secret_key")
    if not region_input:
        raise ValueError("腾讯云 region_id 未配置")

    db_type_aliases = {
        "mysql": "mysql",
        "mariadb": "mysql",
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "pgsql": "postgresql",
        "sqlserver": "sqlserver",
        "sql_server": "sqlserver",
        "mssql": "sqlserver",
        "tdsql-c-mysql": "tdsql_c_mysql",
        "tdsql_c_mysql": "tdsql_c_mysql",
        "cynosdb_mysql": "tdsql_c_mysql",
        "cynosdb-mysql": "tdsql_c_mysql",
    }

    engine_metric_configs = {
        "mysql": {
            "namespace": "QCE/CDB",
            "dimensions": "mysql",
            "metrics": [
                {"remote_name": "CpuUseRate", "metric_name": "cpu_usage", "unit": "%"},
                {"remote_name": "MemoryUseRate", "metric_name": "memory_usage", "unit": "%"},
                {"remote_name": "MemoryUse", "metric_name": "memory_used", "unit": "MB"},
                {"remote_name": "Qps", "metric_name": "qps", "unit": "count/s"},
                {"remote_name": "Tps", "metric_name": "tps", "unit": "count/s"},
                {"remote_name": "Iops", "metric_name": "iops", "unit": "count/s"},
                {"remote_name": "BytesReceived", "metric_name": "network_in", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_rx_bytes"]},
                {"remote_name": "BytesSent", "metric_name": "network_out", "unit": "KB/s", "scale": 1.0 / 1024.0, "aliases": ["network_tx_bytes"]},
                {"remote_name": "RealCapacity", "metric_name": "disk_used", "unit": "MB"},
                {"remote_name": "VolumeRate", "metric_name": "disk_usage", "unit": "%"},
                {"remote_name": "ThreadsConnected", "metric_name": "connections_total", "unit": "count", "aliases": ["threads_connected"]},
                {"remote_name": "ThreadsRunning", "metric_name": "connections_active", "unit": "count", "aliases": ["active_connections", "threads_running"]},
                {"remote_name": "MaxConnections", "metric_name": "max_connections", "unit": "count"},
                {"remote_name": "ConnectionUseRate", "metric_name": "connection_usage_rate", "unit": "%"},
            ],
        },
        "postgresql": {
            "namespace": "QCE/POSTGRES",
            "dimensions": "resource",
            "metrics": [
                {"remote_name": "Cpu", "metric_name": "cpu_usage", "unit": "%"},
                {"remote_name": "MemoryRate", "metric_name": "memory_usage", "unit": "%"},
                {"remote_name": "Memory", "metric_name": "memory_used", "unit": "MB"},
                {"remote_name": "Qps", "metric_name": "qps", "unit": "count/s"},
                {"remote_name": "Tps", "metric_name": "tps", "unit": "count/s"},
                {"remote_name": "Connections", "metric_name": "connections_total", "unit": "count", "aliases": ["total_connections"]},
                {"remote_name": "ActiveConns", "metric_name": "connections_active", "unit": "count", "aliases": ["active_connections"]},
                {"remote_name": "ConnUtilization", "metric_name": "connection_usage_rate", "unit": "%"},
                {"remote_name": "Storage", "metric_name": "disk_used", "unit": "MB", "scale": 1024.0},
                {"remote_name": "StorageRate", "metric_name": "disk_usage", "unit": "%"},
                {"remote_name": "DataFileSize", "metric_name": "disk_data", "unit": "MB", "scale": 1.0 / 1024.0},
                {"remote_name": "LogFileSize", "metric_name": "disk_log", "unit": "MB", "scale": 1.0 / 1024.0},
                {"remote_name": "TempFileSize", "metric_name": "disk_temp", "unit": "MB", "scale": 1.0 / 1024.0},
                {"remote_name": "Throughput", "metric_name": "throughput", "unit": "Bytes/s", "scale": 1024.0},
                {"remote_name": "ThroughputRead", "metric_name": "disk_read_bytes_per_sec", "unit": "Bytes/s", "scale": 1024.0},
                {"remote_name": "ThroughputWrite", "metric_name": "disk_write_bytes_per_sec", "unit": "Bytes/s", "scale": 1024.0},
                {"remote_name": "HitPercent", "metric_name": "cache_hit_rate", "unit": "%", "aliases": ["buffer_pool_hit_rate"]},
                {"remote_name": "SlowQueryCnt", "metric_name": "slow_queries", "unit": "count"},
            ],
        },
        "sqlserver": {
            "namespace": "QCE/SQLSERVER",
            "dimensions": "sqlserver",
            "metrics": [
                {"remote_name": "Cpu", "metric_name": "cpu_usage", "unit": "%"},
                {"remote_name": "UsageMemory", "metric_name": "memory_usage", "unit": "%"},
                {"remote_name": "ServerMemory", "metric_name": "memory_used", "unit": "MB"},
                {"remote_name": "Requests", "metric_name": "qps", "unit": "count/s", "aliases": ["batch_requests_per_sec"]},
                {"remote_name": "Transactions", "metric_name": "tps", "unit": "count/s"},
                {"remote_name": "Connections", "metric_name": "connections_total", "unit": "count", "aliases": ["total_connections"]},
                {"remote_name": "Iops", "metric_name": "iops", "unit": "count/s"},
                {"remote_name": "DiskReadsSec", "metric_name": "disk_reads_per_sec", "unit": "count/s"},
                {"remote_name": "DiskWritesSec", "metric_name": "disk_writes_per_sec", "unit": "count/s"},
                {"remote_name": "InFlow", "metric_name": "network_in", "unit": "KB/s", "aliases": ["network_rx_bytes"]},
                {"remote_name": "OutFlow", "metric_name": "network_out", "unit": "KB/s", "aliases": ["network_tx_bytes"]},
                {"remote_name": "Storage", "metric_name": "disk_used", "unit": "MB", "scale": 1024.0},
                {"remote_name": "FreeStorage", "metric_name": "free_storage_pct", "unit": "%"},
                {"remote_name": "BufferCacheHitRatio", "metric_name": "cache_hit_rate", "unit": "%", "aliases": ["buffer_pool_hit_rate"]},
                {"remote_name": "SlowQueries", "metric_name": "slow_queries", "unit": "count"},
            ],
        },
        "tdsql_c_mysql": {
            "namespace": "QCE/CYNOSDB_MYSQL",
            "dimensions": "instance_only",
            "metrics": [
                {"remote_name": "Cpuuserate", "metric_name": "cpu_usage", "unit": "%"},
                {"remote_name": "Qps", "metric_name": "qps", "unit": "count/s"},
                {"remote_name": "Tps", "metric_name": "tps", "unit": "count/s"},
                {"remote_name": "Readiops", "metric_name": "disk_reads_per_sec", "unit": "count/s"},
                {"remote_name": "Writeiops", "metric_name": "disk_writes_per_sec", "unit": "count/s"},
                {"remote_name": "BytesReceived", "metric_name": "network_in", "unit": "KB/s", "scale": 1024.0, "aliases": ["network_rx_bytes"]},
                {"remote_name": "BytesSent", "metric_name": "network_out", "unit": "KB/s", "scale": 1024.0, "aliases": ["network_tx_bytes"]},
                {"remote_name": "Storageuserate", "metric_name": "disk_usage", "unit": "%"},
                {"remote_name": "DataVolumeUsage", "metric_name": "disk_data", "unit": "MB", "scale": 1024.0},
                {"remote_name": "TmpVolumeUsage", "metric_name": "disk_temp", "unit": "MB", "scale": 1024.0},
                {"remote_name": "UndoVolumeUsage", "metric_name": "disk_undo", "unit": "MB", "scale": 1024.0},
                {"remote_name": "Threadsconnected", "metric_name": "connections_total", "unit": "count", "aliases": ["total_connections", "threads_connected"]},
                {"remote_name": "ThreadsRunning", "metric_name": "connections_active", "unit": "count", "aliases": ["active_connections", "threads_running"]},
                {"remote_name": "Connectionuserate", "metric_name": "connection_usage_rate", "unit": "%"},
                {"remote_name": "InnodbCacheHitRate", "metric_name": "cache_hit_rate", "unit": "%", "aliases": ["buffer_pool_hit_rate"]},
                {"remote_name": "InnodbCacheUseRate", "metric_name": "buffer_pool_usage", "unit": "%"},
            ],
        },
    }

    def normalize_db_type(db_type):
        key = (db_type or "").strip().lower()
        return db_type_aliases.get(key, key)

    def normalize_region(value):
        raw = (value or "").strip().lower().replace("_", "-")
        if not raw:
            return "ap-guangzhou"

        aliases = {
            "1": "ap-guangzhou",
            "gz": "ap-guangzhou",
            "9": "ap-guangzhou-open",
            "gzopen": "ap-guangzhou-open",
            "37": "ap-shenzhen",
            "szx": "ap-shenzhen",
            "8": "ap-shenzhen-fsi",
            "szjr": "ap-shenzhen-fsi",
            "2": "ap-shanghai",
            "sh": "ap-shanghai",
            "5": "ap-shanghai-fsi",
            "shjr": "ap-shanghai-fsi",
            "6": "ap-beijing",
            "bj": "ap-beijing",
            "11": "ap-chengdu",
            "cd": "ap-chengdu",
            "33": "ap-nanjing",
            "nj": "ap-nanjing",
            "14": "ap-chongqing",
            "cq": "ap-chongqing",
            "3": "ap-hongkong",
            "hk": "ap-hongkong",
            "7": "ap-singapore",
            "sg": "ap-singapore",
            "13": "ap-seoul",
            "kr": "ap-seoul",
            "19": "ap-tokyo",
            "jp": "ap-tokyo",
            "17": "ap-bangkok",
            "th": "ap-bangkok",
            "15": "ap-mumbai",
            "in": "ap-mumbai",
            "10": "na-siliconvalley",
            "usw": "na-siliconvalley",
            "16": "na-ashburn",
            "use": "na-ashburn",
            "12": "eu-frankfurt",
            "de": "eu-frankfurt",
        }
        if raw in aliases:
            return aliases[raw]

        if raw.startswith(("ap-", "na-", "eu-", "sa-", "me-", "af-")):
            return raw

        raise ValueError(
            "无效的腾讯云 region_id: "
            + str(value)
            + "。请填写标准地域，例如 ap-guangzhou；也支持监控文档中的地域缩写/数字 ID，例如 gz 或 1"
        )

    def to_float(value, scale=1.0):
        try:
            return round(float(value) * float(scale), 4)
        except (TypeError, ValueError):
            return None

    def to_iso_timestamp(timestamp):
        try:
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    def sha256_hex(content):
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content or b"").hexdigest()

    def hmac_sha256(key, msg):
        if isinstance(key, str):
            key = key.encode("utf-8")
        if isinstance(msg, str):
            msg = msg.encode("utf-8")
        return hmac.new(key, msg, hashlib.sha256).digest()

    region_id = normalize_region(region_input)

    async def call_api(action, payload):
        timestamp = int(time.time())
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        canonical_headers = "content-type:application/json; charset=utf-8\\nhost:" + endpoint + "\\n"
        signed_headers = "content-type;host"
        canonical_request = (
            "POST\\n"
            "/\\n"
            "\\n"
            + canonical_headers
            + "\\n"
            + signed_headers
            + "\\n"
            + sha256_hex(payload_text)
        )
        credential_scope = date + "/" + service + "/tc3_request"
        string_to_sign = (
            "TC3-HMAC-SHA256\\n"
            + str(timestamp)
            + "\\n"
            + credential_scope
            + "\\n"
            + sha256_hex(canonical_request)
        )
        secret_date = hmac_sha256("TC3" + secret_key, date)
        secret_service = hmac_sha256(secret_date, service)
        secret_signing = hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "TC3-HMAC-SHA256 "
            + "Credential="
            + secret_id
            + "/"
            + credential_scope
            + ", SignedHeaders="
            + signed_headers
            + ", Signature="
            + signature
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": endpoint,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
            "X-TC-Region": region_id,
        }
        response = await context.http_request("POST", "https://" + endpoint, data=payload_text, headers=headers)

        raw = response.json()
        if raw is None:
            try:
                raw = json.loads(response.text or "{}")
            except Exception:
                raw = {}

        if response.status_code != 200:
            message = response.text or ("HTTP " + str(response.status_code))
            error = (raw.get("Response") or {}).get("Error") if isinstance(raw, dict) else None
            if isinstance(error, dict):
                message = error.get("Code", "Unknown") + ": " + error.get("Message", "Unknown error")
            raise ValueError(message)

        body = raw.get("Response") if isinstance(raw, dict) else None
        if not isinstance(body, dict):
            raise ValueError("腾讯云 API 返回数据格式异常")

        error = body.get("Error")
        if isinstance(error, dict):
            raise ValueError(error.get("Code", "Unknown") + ": " + error.get("Message", "Unknown error"))

        return body

    async def validate_credentials():
        def is_network_error(error):
            error_name = type(error).__name__
            error_text = str(error).lower()
            network_error_names = {
                "ClientConnectorError",
                "ClientConnectorDNSError",
                "ClientConnectionError",
                "ClientOSError",
                "ServerTimeoutError",
                "TimeoutError",
            }
            if error_name in network_error_names:
                return True
            network_keywords = [
                "timeout while contacting dns servers",
                "name or service not known",
                "temporary failure in name resolution",
                "nodename nor servname provided",
                "failed to resolve",
                "cannot connect to host",
                "connection timeout",
                "connection timed out",
                "dns",
            ]
            return any(keyword in error_text for keyword in network_keywords)

        try:
            await call_api("DescribeAllNamespaces", {
                "Module": "monitor",
                "MonitorTypes": ["MT_QCE"],
                "SceneType": "ST_ALARM",
            })
        except Exception as e:
            if is_network_error(e):
                raise ValueError("腾讯云 API 网络连接失败，请检查 DNS/网络配置: " + str(e))
            raise ValueError("腾讯云 SecretId/SecretKey 验证失败，请检查配置: " + str(e))

    def build_dimensions(mode, instance_id):
        if mode == "mysql":
            dimensions = [{"Name": "InstanceId", "Value": instance_id}]
            if mysql_instance_type:
                dimensions.append({"Name": "InstanceType", "Value": mysql_instance_type})
            return dimensions
        if mode == "resource":
            return [{"Name": "resourceId", "Value": instance_id}]
        if mode == "sqlserver":
            return [
                {"Name": "resourceId", "Value": instance_id},
                {"Name": "RegionId", "Value": region_id},
            ]
        return [{"Name": "InstanceId", "Value": instance_id}]

    def extract_latest_datapoint(body):
        latest_timestamp = None
        latest_value = None
        for item in body.get("DataPoints") or []:
            timestamps = item.get("Timestamps") or []
            values = item.get("Values") or []
            size = min(len(timestamps), len(values))
            for index in range(size):
                ts = timestamps[index]
                try:
                    current_ts = float(ts)
                except (TypeError, ValueError):
                    continue
                if latest_timestamp is None or current_ts >= float(latest_timestamp):
                    latest_timestamp = ts
                    latest_value = values[index]
        return latest_timestamp, latest_value

    def build_metric_point(datasource_id, instance_id, metric_name, metric_value, unit, timestamp=None):
        point = {
            "datasource_id": datasource_id,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "labels": {
                "source": "tencentcloud_rds",
                "instance_id": instance_id,
                "unit": unit,
            },
        }
        if timestamp:
            point["timestamp"] = timestamp
        return point

    def append_metric(metrics_map, datasource_id, instance_id, metric_name, value, unit, timestamp=None, aliases=None):
        metrics_map[metric_name] = build_metric_point(datasource_id, instance_id, metric_name, value, unit, timestamp)
        for alias in aliases or []:
            metrics_map[alias] = build_metric_point(datasource_id, instance_id, alias, value, unit, timestamp)

    def fill_total_from_usage(metrics_map, used_key, usage_key, total_key):
        used = metrics_map.get(used_key)
        usage = metrics_map.get(usage_key)
        if not used or not usage:
            return
        usage_value = usage.get("metric_value")
        used_value = used.get("metric_value")
        if usage_value in (None, 0) or used_value is None:
            return
        try:
            total_value = round(float(used_value) / (float(usage_value) / 100.0), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            return
        append_metric(
            metrics_map,
            used["datasource_id"],
            used["labels"]["instance_id"],
            total_key,
            total_value,
            used["labels"].get("unit", "MB"),
            used.get("timestamp"),
        )

    def fill_max_connections(metrics_map, current_key, usage_key):
        current = metrics_map.get(current_key)
        usage = metrics_map.get(usage_key)
        if not current or not usage:
            return
        current_value = current.get("metric_value")
        usage_value = usage.get("metric_value")
        if current_value is None or usage_value in (None, 0):
            return
        try:
            max_value = round(float(current_value) / (float(usage_value) / 100.0), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            return
        append_metric(
            metrics_map,
            current["datasource_id"],
            current["labels"]["instance_id"],
            "max_connections",
            max_value,
            "count",
            current.get("timestamp"),
        )

    await validate_credentials()

    metrics = []
    if not datasource:
        await context.log("info", "没有配置数据源，腾讯云凭证验证已通过")
        return metrics

    end_time = datetime.now(timezone.utc).replace(microsecond=0)
    start_time = end_time - timedelta(minutes=30)
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    # 使用 300 秒粒度，覆盖四类数据库公共监控指标。
    period = 300

    for ds in datasource:
        db_type = normalize_db_type(ds.get("db_type"))
        if db_type not in engine_metric_configs:
            raise ValueError("数据源 " + ds["name"] + " 的数据库类型暂不支持腾讯云 RDS 外部采集: " + str(ds.get("db_type")))

        instance_id = (ds.get("external_instance_id") or "").strip()
        if not instance_id:
            raise ValueError("数据源 " + ds["name"] + " 未配置 external_instance_id")

        config = engine_metric_configs[db_type]
        dimensions = build_dimensions(config["dimensions"], instance_id)
        latest_metrics = {}
        successful_metric_count = 0
        last_error = None

        for metric_def in config["metrics"]:
            payload = {
                "Namespace": config["namespace"],
                "MetricName": metric_def["remote_name"],
                "Instances": [{"Dimensions": dimensions}],
                "Period": period,
                "StartTime": start_time_str,
                "EndTime": end_time_str,
            }

            try:
                body = await call_api("GetMonitorData", payload)
                timestamp_raw, raw_value = extract_latest_datapoint(body)
                value = to_float(raw_value, metric_def.get("scale", 1.0))
                if value is None:
                    continue
                successful_metric_count += 1
                timestamp = to_iso_timestamp(timestamp_raw)
                append_metric(
                    latest_metrics,
                    ds["id"],
                    instance_id,
                    metric_def["metric_name"],
                    value,
                    metric_def["unit"],
                    timestamp,
                    metric_def.get("aliases"),
                )
            except Exception as e:
                last_error = str(e)
                await context.log(
                    "warning",
                    "腾讯云指标 "
                    + metric_def["remote_name"]
                    + " 采集失败（数据源 "
                    + ds["name"]
                    + "）: "
                    + str(e),
                )

        if db_type == "mysql":
            fill_total_from_usage(latest_metrics, "disk_used", "disk_usage", "disk_total")
            fill_max_connections(latest_metrics, "connections_total", "connection_usage_rate")
        elif db_type == "postgresql":
            fill_total_from_usage(latest_metrics, "disk_used", "disk_usage", "disk_total")
            fill_max_connections(latest_metrics, "connections_total", "connection_usage_rate")
        elif db_type == "sqlserver":
            free_storage = latest_metrics.get("free_storage_pct")
            if free_storage and free_storage.get("metric_value") is not None:
                used_pct = round(100.0 - float(free_storage["metric_value"]), 4)
                append_metric(
                    latest_metrics,
                    ds["id"],
                    instance_id,
                    "disk_usage",
                    used_pct,
                    "%",
                    free_storage.get("timestamp"),
                )
            fill_total_from_usage(latest_metrics, "disk_used", "disk_usage", "disk_total")
        elif db_type == "tdsql_c_mysql":
            data_space = latest_metrics.get("disk_data", {}).get("metric_value", 0) or 0
            tmp_space = latest_metrics.get("disk_temp", {}).get("metric_value", 0) or 0
            undo_space = latest_metrics.get("disk_undo", {}).get("metric_value", 0) or 0
            total_used = round(float(data_space) + float(tmp_space) + float(undo_space), 4)
            if total_used > 0:
                append_metric(
                    latest_metrics,
                    ds["id"],
                    instance_id,
                    "disk_used",
                    total_used,
                    "MB",
                    latest_metrics.get("disk_data", {}).get("timestamp"),
                )
            fill_total_from_usage(latest_metrics, "disk_used", "disk_usage", "disk_total")
            fill_max_connections(latest_metrics, "connections_total", "connection_usage_rate")
            read_iops = latest_metrics.get("disk_reads_per_sec", {}).get("metric_value")
            write_iops = latest_metrics.get("disk_writes_per_sec", {}).get("metric_value")
            if read_iops is not None or write_iops is not None:
                append_metric(
                    latest_metrics,
                    ds["id"],
                    instance_id,
                    "iops",
                    round(float(read_iops or 0) + float(write_iops or 0), 4),
                    "count/s",
                    latest_metrics.get("disk_reads_per_sec", {}).get("timestamp") or latest_metrics.get("disk_writes_per_sec", {}).get("timestamp"),
                )

        if not latest_metrics:
            if last_error:
                raise ValueError("腾讯云 API 调用失败: " + last_error)
            raise ValueError(
                "腾讯云监控未返回实例 "
                + instance_id
                + " 的有效监控数据，请确认 external_instance_id、region_id 以及实例类型与数据源 db_type 是否匹配"
            )

        metrics.extend(latest_metrics.values())
        await context.log(
            "info",
            "成功采集数据源 "
            + ds["name"]
            + " 的 "
            + str(len(latest_metrics))
            + " 条腾讯云指标（成功请求 "
            + str(successful_metric_count)
            + " 个监控项）",
        )

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

DINGTALK_BOT_TEMPLATE = {
    "integration_id": "builtin_dingtalk_bot",
    "name": "钉钉机器人对话",
    "description": "钉钉机器人入站对话配置，使用 Stream Mode 长连接接收消息并回复",
    "integration_type": "bot",
    "category": "im",
    "config_schema": {"type": "object", "properties": {}, "required": []},
    "code": "CLIENT_ID = \"\"\nCLIENT_SECRET = \"\"\n\nasync def handle_event(context, params, payload):\n    return {\"success\": True, \"message\": \"DingTalk bot is handled by dedicated stream service\"}\n"
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
    DINGTALK_BOT_TEMPLATE,
    WEIXIN_BOT_TEMPLATE,
    DINGTALK_WEBHOOK_TEMPLATE,
    EMAIL_TEMPLATE,
    GENERIC_WEBHOOK_TEMPLATE,
    ALIYUN_RDS_TEMPLATE,
    HUAWEI_CLOUD_RDS_TEMPLATE,
    TENCENT_CLOUD_RDS_TEMPLATE
]
