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
    "code": """import time
import hmac
import hashlib
import base64

async def send_notification(context, params, payload):
    webhook_url = params.get("webhook_url")
    secret = params.get("secret")

    # 构建飞书交互式卡片
    severity_colors = {
        "critical": "red",
        "warning": "orange",
        "info": "blue"
    }

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": payload["title"]
                },
                "template": severity_colors.get(payload["severity"], "blue")
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": payload["content"]
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**数据源**\\n{payload['datasource_name']}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**时间**\\n{payload['timestamp']}"}}
                    ]
                }
            ]
        }
    }

    actions = []
    if payload.get("alert_url"):
        actions.append({
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "查看告警详情"
            },
            "type": "primary",
            "multi_url": {
                "url": payload["alert_url"],
                "pc_url": payload["alert_url"],
                "android_url": payload["alert_url"],
                "ios_url": payload["alert_url"]
            }
        })
    if payload.get("report_url"):
        actions.append({
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "查看诊断报告"
            },
            "type": "default",
            "multi_url": {
                "url": payload["report_url"],
                "pc_url": payload["report_url"],
                "android_url": payload["report_url"],
                "ios_url": payload["report_url"]
            }
        })
    if actions:
        card["card"]["elements"].append({
            "tag": "action",
            "actions": actions
        })

    # 签名（如果提供了 secret）
    headers = {"Content-Type": "application/json"}
    if secret:
        timestamp = str(int(time.time()))
        sign_string = f"{timestamp}\\n{secret}"
        sign = base64.b64encode(hmac.new(
            sign_string.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()).decode("utf-8")
        card["timestamp"] = timestamp
        card["sign"] = sign

    # 发送请求
    response = await context.http_request("POST", webhook_url, json=card, headers=headers)

    if response.status_code == 200:
        return {"success": True, "message": "飞书通知发送成功"}
    else:
        return {"success": False, "message": f"飞书通知发送失败: {response.text}"}
"""
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
    "code": """import time
import hmac
import hashlib
import base64
import urllib.parse

async def send_notification(context, params, payload):
    webhook_url = params["webhook_url"]
    secret = params.get("secret")

    # 构建钉钉 Markdown 消息
    severity_emoji = {
        "critical": "🔴",
        "warning": "🟠",
        "info": "🔵"
    }

    markdown_text = f\"\"\"### {severity_emoji.get(payload['severity'], '')} {payload['title']}

{payload['content']}

---

**数据源**: {payload['datasource_name']}
**时间**: {payload['timestamp']}
\"\"\"

    message = {
        "msgtype": "markdown",
        "markdown": {
            "title": payload["title"],
            "text": markdown_text
        }
    }

    # 签名（可选）
    signed_url = webhook_url
    if secret:
        timestamp = str(int(time.time() * 1000))
        sign_string = f"{timestamp}\\n{secret}"
        sign = base64.b64encode(hmac.new(
            secret.encode("utf-8"),
            sign_string.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()).decode("utf-8")
        signed_url = f"{webhook_url}&timestamp={timestamp}&sign={urllib.parse.quote(sign)}"

    # 发送请求
    response = await context.http_request("POST", signed_url, json=message)

    if response.status_code == 200:
        result = response.json()
        if result.get("errcode") == 0:
            return {"success": True, "message": "钉钉通知发送成功"}
        else:
            return {"success": False, "message": f"钉钉通知发送失败: {result.get('errmsg')}"}
    else:
        return {"success": False, "message": f"钉钉通知发送失败: {response.text}"}
"""
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
    "code": """import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

async def send_notification(context, params, payload):
    # 从系统配置读取 SMTP 配置
    smtp_host = await context.get_system_config("smtp_host")
    smtp_port = await context.get_system_config("smtp_port")
    smtp_username = await context.get_system_config("smtp_username")
    smtp_password = await context.get_system_config("smtp_password")
    smtp_from_email = await context.get_system_config("smtp_from_email")
    smtp_use_tls = await context.get_system_config("smtp_use_tls")

    if not all([smtp_host, smtp_port, smtp_username, smtp_password, smtp_from_email]):
        return {"success": False, "message": "SMTP 配置不完整，请在系统配置中设置"}

    # 构建邮件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = payload["title"]
    msg["From"] = smtp_from_email
    msg["To"] = params["to"]
    if params.get("cc"):
        msg["Cc"] = params["cc"]

    # HTML 内容
    severity_colors = {
        "critical": "#ff4d4f",
        "warning": "#faad14",
        "info": "#1890ff"
    }

    html = f\"\"\"
    <html>
    <body style="font-family: Arial, sans-serif;">
        <div style="border-left: 4px solid {severity_colors.get(payload['severity'], '#1890ff')}; padding-left: 16px;">
            <h2>{payload['title']}</h2>
            <p>{payload['content'].replace(chr(10), '<br>')}</p>
            <hr>
            <p><strong>数据源:</strong> {payload['datasource_name']}</p>
            <p><strong>时间:</strong> {payload['timestamp']}</p>
        </div>
    </body>
    </html>
    \"\"\"

    msg.attach(MIMEText(html, "html"))

    # 同步发送邮件的函数
    def send_email_sync():
        server = None
        try:
            port = int(smtp_port)

            # 根据端口和配置选择连接方式
            # 端口 465 通常使用 SSL，端口 25/587 使用 STARTTLS
            if port == 465 or smtp_use_tls == "ssl":
                # 使用 SSL 连接
                server = smtplib.SMTP_SSL(smtp_host, port, timeout=20)
            else:
                # 使用普通连接，然后 STARTTLS
                server = smtplib.SMTP(smtp_host, port, timeout=20)
                if smtp_use_tls == "true":
                    server.starttls()

            # 登录
            server.login(smtp_username, smtp_password)

            # 发送邮件
            recipients = [r.strip() for r in params["to"].split(",")]
            if params.get("cc"):
                recipients.extend([r.strip() for r in params["cc"].split(",")])

            server.sendmail(smtp_from_email, recipients, msg.as_string())

            return {"success": True, "message": "邮件发送成功"}

        except smtplib.SMTPAuthenticationError as e:
            return {"success": False, "message": f"SMTP 认证失败，请检查用户名和密码: {str(e)}"}
        except smtplib.SMTPConnectError as e:
            return {"success": False, "message": f"无法连接到 SMTP 服务器 {smtp_host}:{smtp_port}: {str(e)}"}
        except TimeoutError as e:
            return {"success": False, "message": f"连接 SMTP 服务器超时，请检查服务器地址和端口: {smtp_host}:{smtp_port}"}
        except Exception as e:
            return {"success": False, "message": f"邮件发送失败: {type(e).__name__}: {str(e)}"}
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass

    # 在线程池中执行同步操作
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_thread_pool, send_email_sync)
    return result
"""
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
    "code": """async def send_notification(context, params, payload):
    webhook_url = params["webhook_url"]
    method = params.get("method", "POST")
    auth_type = params.get("auth_type", "none")
    auth_token = params.get("auth_token")

    # 构建请求头
    headers = {"Content-Type": "application/json"}

    # 添加认证
    if auth_type == "bearer" and auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    elif auth_type == "basic" and auth_token:
        headers["Authorization"] = f"Basic {auth_token}"

    # 构建 payload
    webhook_payload = {
        "title": payload["title"],
        "content": payload["content"],
        "severity": payload["severity"],
        "datasource_name": payload["datasource_name"],
        "alert_id": payload["alert_id"],
        "timestamp": payload["timestamp"]
    }

    # 发送请求
    response = await context.http_request(method, webhook_url, json=webhook_payload, headers=headers)

    if 200 <= response.status_code < 300:
        return {"success": True, "message": f"Webhook 通知发送成功 (HTTP {response.status_code})"}
    else:
        return {"success": False, "message": f"Webhook 通知发送失败: HTTP {response.status_code}, {response.text}"}
"""
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
    # 从系统配置中读取阿里云凭证
    access_key_id = await context.get_system_config("aliyun_access_key_id")
    access_key_secret = await context.get_system_config("aliyun_access_key_secret")

    # 验证凭证配置
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云 AccessKey 未配置，请在系统配置中设置 aliyun_access_key_id 和 aliyun_access_key_secret")

    # 从参数中获取地域 ID
    region_id = params.get("region_id", "cn-hangzhou")

    # 导入阿里云 SDK
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkrds.request.v20140815 import DescribeDBInstancePerformanceRequest
    except ImportError:
        raise ValueError("阿里云 SDK 未安装，请运行: pip install aliyun-python-sdk-core aliyun-python-sdk-rds")

    from datetime import datetime, timedelta
    import json

    # 创建阿里云客户端
    client = AcsClient(access_key_id, access_key_secret, region_id)

    metrics = []

    # 定义要采集的指标及其映射关系
    # 格式: (阿里云指标名, [(SmartDBA指标名, 值索引, 单位)])
    metric_mappings = {
        "MySQL_MemCpuUsage": [
            ("cpu_usage", 0, "%"),            # CPU 使用率
            ("memory_usage", 1, "%")          # 内存使用率
        ],
        "MySQL_DetailedSpaceUsage": [
            ("disk_total", 0, "MB"),          # 总空间
            ("disk_data", 1, "MB"),           # 数据空间
            ("disk_log", 2, "MB"),            # 日志空间
            ("disk_temp", 3, "MB"),           # 临时空间
            ("disk_system", 4, "MB")          # 系统空间
        ],
        "MySQL_IOPS": [
            ("disk_reads_per_sec", 0, "次/秒"),
            ("disk_writes_per_sec", 0, "次/秒")
        ],
        "MySQL_NetworkTraffic": [
            ("network_rx_bytes", 0, "KB/秒"),
            ("network_tx_bytes", 1, "KB/秒")
        ],
        "MySQL_QPSTPS": [
            ("qps", 0, "次/秒"),              # QPS
            ("tps", 1, "个/秒")               # TPS
        ],
        "MySQL_Sessions": [
            ("connections_active", 0, "个"),  # 活跃连接
            ("connections_total", 1, "个")    # 总连接
        ]
    }

    for ds in datasources:
        instance_id = ds.get("external_instance_id")
        if not instance_id:
            raise ValueError(f"数据源 {ds['name']} 未配置 external_instance_id，无法采集阿里云 RDS 监控数据。请在数据源配置中设置 external_instance_id 为阿里云 RDS 实例 ID（如 rm-bp1xxx）")

        try:
            # 查询最近 1 小时的监控数据
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)

            # 构建要查询的指标列表
            keys = ",".join(metric_mappings.keys())

            # 创建请求
            request = DescribeDBInstancePerformanceRequest.DescribeDBInstancePerformanceRequest()
            request.set_DBInstanceId(instance_id)
            request.set_Key(keys)
            request.set_StartTime(start_time.strftime("%Y-%m-%dT%H:%MZ"))
            request.set_EndTime(end_time.strftime("%Y-%m-%dT%H:%MZ"))

            # 发送请求
            response = client.do_action_with_exception(request)
            data = json.loads(response)

            # 解析性能数据
            perf_keys = data.get("PerformanceKeys", {}).get("PerformanceKey", [])

            # 用于存储每个指标的最新值
            latest_metrics = {}

            for perf_key in perf_keys:
                metric_name = perf_key.get("Key")
                values = perf_key.get("Values", {}).get("PerformanceValue", [])

                # 获取该指标的映射配置
                mappings = metric_mappings.get(metric_name, [])

                # 只取最新的数据点（最后一个）
                if values:
                    point = values[-1]  # 取最后一个点（最新的）
                    value_str = point.get("Value", "")

                    # 阿里云返回的值可能是多个值用 & 分隔（如 "5.13&0.33"）
                    value_parts = value_str.split("&") if value_str else []

                    # 根据映射配置解析每个值
                    for smartdba_name, index, unit in mappings:
                        if index < len(value_parts):
                            try:
                                value = float(value_parts[index])
                                latest_metrics[smartdba_name] = {
                                    "datasource_id": ds["id"],
                                    "metric_name": smartdba_name,
                                    "metric_value": value,
                                    "labels": {
                                        "source": "aliyun_rds",
                                        "instance_id": instance_id,
                                        "unit": unit
                                    }
                                }
                            except (ValueError, TypeError) as e:
                                await context.log("warning", f"无法解析指标 {smartdba_name} 的值: {value_parts[index]}")
                                continue

            # 将最新指标添加到结果中（不包含时间戳，由调度器统一设置）
            metrics.extend(latest_metrics.values())

            await context.log("info", f"成功采集数据源 {ds['name']} 的 {len(latest_metrics)} 条指标")

        except Exception as e:
            error_msg = str(e)
            await context.log("error", f"采集数据源 {ds['name']} 失败: {error_msg}")
            raise ValueError(f"阿里云 API 调用失败: {error_msg}")

    return metrics
"""
}

# 所有内置模板
FEISHU_BOT_TEMPLATE = {
    "integration_id": "builtin_feishu_bot",
    "name": "飞书机器人对话",
    "description": "飞书机器人入站对话配置，用于数据库诊断会话",
    "integration_type": "bot",
    "category": "im",
    "config_schema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "code": "# 直接修改下面 3 个常量来配置飞书机器人凭据\nAPP_ID = \"\"\nAPP_SECRET = \"\"\nSIGNING_SECRET = \"\"\n\nasync def handle_event(context, params, payload):\n    return {'success': True, 'message': 'Feishu bot is handled by dedicated router/service'}\n"
}

WEIXIN_BOT_TEMPLATE = {
    "integration_id": "builtin_weixin_bot",
    "name": "微信机器人对话",
    "description": "微信机器人入站对话配置（OpenClaw 协议），通过长轮询收消息并回复",
    "integration_type": "bot",
    "category": "im",
    "config_schema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "code": "# 微信机器人由后台轮询服务处理（weixin_bot_service）。\n# 这里不需要可执行代码，仅作为内置 Bot 类型的配置入口。\n\nasync def handle_event(context, params, payload):\n    return {'success': True, 'message': 'Weixin bot is handled by dedicated poller/service'}\n"
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
