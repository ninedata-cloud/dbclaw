from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from datetime import datetime, time as dt_time
import logging
import re
import smtplib
import aiohttp
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from backend.models.alert_message import AlertMessage
from backend.models.alert_subscription import AlertSubscription
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.models.user import User
from backend.models.system_config import SystemConfig
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter
from backend.utils.datetime_helper import now, format_local_datetime

logger = logging.getLogger(__name__)


class NotificationService:
    """Notification dispatch service"""

    @staticmethod
    def _format_diagnosis_markdown(text: Optional[str], *, max_items: int = 5) -> Optional[str]:
        content = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not content:
            return None

        raw_items = content.splitlines() if "\n" in content else re.split(r"[；;]\s*", content)
        items: list[str] = []
        seen: set[str] = set()
        for raw in raw_items:
            line = re.sub(r"^[\-\*\u2022]+\s*", "", str(raw or "").strip())
            line = re.sub(r"^\d+[\.\)、]\s*", "", line).strip()
            line = line.strip("：:；; ")
            if not line:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(line)
            if len(items) >= max_items:
                break

        if not items:
            return None
        if len(items) == 1:
            return items[0]
        return "\n".join(f"- {item}" for item in items)

    @staticmethod
    @staticmethod
    async def check_subscription_match(
        alert: AlertMessage,
        subscription: AlertSubscription
    ) -> bool:
        """
        Check if alert matches subscription filters.

        Returns True if:
        1. Datasource matches (or subscription has no datasource filter)
        2. Severity matches (or subscription has no severity filter)
        3. Current time is within time ranges (or subscription has no time filter)
        """
        # Check datasource filter
        # datasource_id=0 means system-level alert (e.g. network probe), bypass datasource filter
        if subscription.datasource_ids and alert.datasource_id != 0:
            if alert.datasource_id not in subscription.datasource_ids:
                return False

        # Check severity filter
        if subscription.severity_levels:
            if alert.severity not in subscription.severity_levels:
                return False

        # Check time range filter
        if subscription.time_ranges:
            current_time = now()
            current_hour = current_time.hour
            current_minute = current_time.minute
            current_weekday = current_time.weekday()  # 0=Monday, 6=Sunday

            matched = False
            for time_range in subscription.time_ranges:
                # Check if current weekday is in allowed days
                if current_weekday not in time_range['days']:
                    continue

                # Parse start and end times (format: "HH:MM")
                start_hour, start_minute = map(int, time_range['start'].split(':'))
                end_hour, end_minute = map(int, time_range['end'].split(':'))

                # Convert to minutes for easier comparison
                current_minutes = current_hour * 60 + current_minute
                start_minutes = start_hour * 60 + start_minute
                end_minutes = end_hour * 60 + end_minute

                # Check if current time is within range
                if start_minutes <= current_minutes <= end_minutes:
                    matched = True
                    break

            if not matched:
                return False

        return True

    @staticmethod
    async def send_notifications(
        db: AsyncSession,
        alert: AlertMessage,
        subscription: AlertSubscription
    ) -> List[AlertDeliveryLog]:
        """
        Send notifications for an alert based on subscription channels.
        Delegates to the Integration system for actual delivery.

        Args:
            db: Database session
            alert: Alert to send
            subscription: Subscription configuration

        Returns:
            List of delivery log entries
        """
        from backend.services.notification_dispatcher import _send_via_integration

        if not subscription.integration_targets:
            logger.warning(f"Subscription {subscription.id} has no integration targets configured")
            return []

        return await _send_via_integration(db, alert, subscription)

    @staticmethod
    async def _send_email(
        db: AsyncSession,
        alert: AlertMessage,
        recipient: str,
        subscription_id: int,
        datasource: Optional[Any] = None
    ) -> AlertDeliveryLog:
        """Send email notification"""
        log = AlertDeliveryLog(
            alert_id=alert.id,
            subscription_id=subscription_id,
            channel="email",
            recipient=recipient,
            status="pending"
        )
        db.add(log)

        try:
            # Get SMTP configuration
            config_result = await db.execute(
                select(SystemConfig).where(SystemConfig.category == "notification")
            )
            configs = {c.key: c.value for c in config_result.scalars().all()}

            smtp_host = configs.get("smtp_host")
            smtp_port = int(configs.get("smtp_port", 587))
            smtp_username = configs.get("smtp_username")
            smtp_password = configs.get("smtp_password")
            smtp_from = configs.get("smtp_from_email")
            smtp_use_tls = configs.get("smtp_use_tls", "true").lower() == "true"

            if not all([smtp_host, smtp_username, smtp_password, smtp_from]):
                raise ValueError("SMTP configuration incomplete")

            # Create email message
            msg = MIMEMultipart()
            msg['From'] = smtp_from
            msg['To'] = recipient
            msg['Subject'] = f"[{NotificationService._map_severity(alert.severity)}] {alert.title}"

            ds_info = ""
            if datasource:
                ds_info = f"""\n数据库信息：
--------------
名称：{datasource.name}
类型：{datasource.db_type.upper()}
地址：{datasource.host}:{datasource.port}
数据库：{datasource.database or '无'}
"""

            body = f"""
告警详情：
--------------
严重程度：{NotificationService._map_severity(alert.severity)}
告警类型：{NotificationService._map_alert_type(alert.alert_type)}
{ds_info}
{alert.content}

创建时间：{format_local_datetime(alert.created_at)}
"""
            msg.attach(MIMEText(body, 'plain'))
            if smtp_use_tls:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
            try:
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
            finally:
                server.quit()

            log.status = "sent"
            log.sent_at = now()
            logger.info(f"Email sent to {recipient} for alert {alert.id}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"Failed to send email to {recipient}: {e}")

        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def _send_sms(
        db: AsyncSession,
        alert: AlertMessage,
        recipient: str,
        subscription_id: int,
        datasource: Optional[Any] = None
    ) -> AlertDeliveryLog:
        """Send SMS notification"""
        log = AlertDeliveryLog(
            alert_id=alert.id,
            subscription_id=subscription_id,
            channel="sms",
            recipient=recipient,
            status="pending"
        )
        db.add(log)

        try:
            # Get SMS configuration
            config_result = await db.execute(
                select(SystemConfig).where(SystemConfig.category == "notification")
            )
            configs = {c.key: c.value for c in config_result.scalars().all()}

            sms_provider = configs.get("sms_provider", "webhook")

            if sms_provider == "webhook":
                webhook_url = configs.get("sms_webhook_url")
                if not webhook_url:
                    raise ValueError("SMS webhook URL not configured")

                ds_prefix = f"[{datasource.name}/{datasource.db_type.upper()}] " if datasource else ""
                # Send via webhook
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "phone": recipient,
                        "message": f"[{NotificationService._map_severity(alert.severity)}告警] {ds_prefix}{alert.title}: {alert.content[:100]}"
                    }
                    async with session.post(webhook_url, json=payload) as response:
                        if response.status != 200:
                            raise Exception(f"Webhook returned status {response.status}")

            else:
                # Placeholder for Aliyun/Twilio integration
                raise NotImplementedError(f"SMS provider {sms_provider} not implemented")

            log.status = "sent"
            log.sent_at = now()
            logger.info(f"SMS sent to {recipient} for alert {alert.id}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"Failed to send SMS to {recipient}: {e}")

        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def _send_phone(
        db: AsyncSession,
        alert: AlertMessage,
        recipient: str,
        subscription_id: int,
        datasource: Optional[Any] = None
    ) -> AlertDeliveryLog:
        """Send phone call notification"""
        log = AlertDeliveryLog(
            alert_id=alert.id,
            subscription_id=subscription_id,
            channel="phone",
            recipient=recipient,
            status="pending"
        )
        db.add(log)

        try:
            # Get phone configuration
            config_result = await db.execute(
                select(SystemConfig).where(SystemConfig.category == "notification")
            )
            configs = {c.key: c.value for c in config_result.scalars().all()}

            phone_provider = configs.get("phone_provider", "webhook")

            if phone_provider == "webhook":
                webhook_url = configs.get("phone_webhook_url")
                if not webhook_url:
                    raise ValueError("Phone webhook URL not configured")

                ds_prefix = f"[{datasource.name}/{datasource.db_type.upper()}] " if datasource else ""
                # Send via webhook
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "phone": recipient,
                        "message": f"[告警] {ds_prefix}{alert.title}，严重程度：{NotificationService._map_severity(alert.severity)}"
                    }
                    async with session.post(webhook_url, json=payload) as response:
                        if response.status != 200:
                            raise Exception(f"Webhook returned status {response.status}")

            else:
                # Placeholder for Aliyun/Twilio integration
                raise NotImplementedError(f"Phone provider {phone_provider} not implemented")

            log.status = "sent"
            log.sent_at = now()
            logger.info(f"Phone call sent to {recipient} for alert {alert.id}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"Failed to send phone call to {recipient}: {e}")

        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def send_recovery_notifications(
        db: AsyncSession,
        alert: AlertMessage,
        subscription: AlertSubscription
    ) -> List[AlertDeliveryLog]:
        """
        Send recovery notifications for a resolved alert.

        Note: This method is deprecated. Recovery notifications should be sent
        via the Integration system using integration_targets.
        """
        logger.warning(
            f"send_recovery_notifications is deprecated for subscription {subscription.id}. "
            "Use Integration system instead."
        )
        return []

    @staticmethod
    @staticmethod
    def _is_feishu_webhook(url: str) -> bool:
        """Check if URL is a Feishu/Lark webhook"""
        return 'open.feishu.cn' in url or 'open.larksuite.com' in url

    @staticmethod
    def _is_dingtalk_webhook(url: str) -> bool:
        """Check if URL is a DingTalk webhook"""
        return 'oapi.dingtalk.com' in url

    @staticmethod
    def _map_severity(severity: str) -> str:
        """Map severity code to Chinese label"""
        labels = {'critical': '严重', 'high': '高', 'medium': '中', 'low': '低'}
        return labels.get(severity, severity)

    @staticmethod
    def _map_alert_type(alert_type: str) -> str:
        """Map alert_type code to Chinese label"""
        labels = {
            'threshold_violation': '超过阈值',
            'baseline_deviation': '偏离基线',
            'custom_expression': '自定义表达式',
            'system_error': '系统错误',
            'ai_policy_violation': 'AI 判警',
        }
        return labels.get(alert_type, alert_type)

    @staticmethod
    def _build_dingtalk_url(webhook_url: str, secret: Optional[str]) -> str:
        """Build signed DingTalk webhook URL if secret provided"""
        if not secret:
            return webhook_url
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return f'{webhook_url}&timestamp={timestamp}&sign={sign}'

    @staticmethod
    def _build_dingtalk_payload(alert: AlertMessage, datasource=None) -> dict:
        """Build DingTalk markdown message payload"""
        severity_label = NotificationService._map_severity(alert.severity)
        alert_type_label = NotificationService._map_alert_type(alert.alert_type)
        lines = [f'### [{severity_label}] {alert.title}']
        if datasource:
            lines.append(f'**数据库：** {datasource.name} ({datasource.db_type.upper()}) {datasource.host}:{datasource.port}')
        lines.append(f'**告警类型：** {alert_type_label}')
        if alert.metric_name and alert.metric_value is not None:
            lines.append(f'**指标：** {alert.metric_name} = {alert.metric_value:.2f}')
        if alert.threshold_value is not None:
            lines.append(f'**阈值：** {alert.threshold_value:.2f}')
        if alert.trigger_reason:
            lines.append(f'**触发原因：** {alert.trigger_reason}')
        lines.append(f'**时间：** {format_local_datetime(alert.created_at)}')
        return {
            'msgtype': 'markdown',
            'markdown': {
                'title': f'[{severity_label}] {alert.title}',
                'text': '\n\n'.join(lines)
            }
        }

    @staticmethod
    @staticmethod
    def _build_feishu_payload(alert: AlertMessage, datasource=None) -> dict:
        """Build Feishu-compatible card message payload"""
        severity = (alert.severity or '').lower()
        severity_colors = {
            'critical': 'red',
            'high': 'red',
            'medium': 'orange',
            'low': 'orange'
        }
        color = severity_colors.get(severity, 'blue')
        severity_label = NotificationService._map_severity(alert.severity)
        alert_type_label = NotificationService._map_alert_type(alert.alert_type)

        elements = []

        # 告警信息
        alert_info = [
            f"**告警标题：** {alert.title}",
            f"**严重程度：** {severity_label}",
            f"**告警类型：** {alert_type_label}",
        ]
        is_ai_policy = (alert.alert_type or "") == "ai_policy_violation"
        if alert.metric_name and alert.metric_value is not None:
            alert_info.append(f"**指标：** {alert.metric_name} = {alert.metric_value:.2f}")
        elif alert.metric_name and not is_ai_policy:
            alert_info.append(f"**指标：** {alert.metric_name}")
        if alert.threshold_value is not None:
            alert_info.append(f"**阈值：** {alert.threshold_value:.2f}")
        if alert.trigger_reason:
            alert_info.append(f"**触发原因：** {alert.trigger_reason}")
        alert_info.append(f"**触发时间：** {format_local_datetime(alert.created_at)}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(alert_info)}})

        root_cause_markdown = NotificationService._format_diagnosis_markdown(getattr(alert, "root_cause", None))
        recommended_actions_markdown = NotificationService._format_diagnosis_markdown(getattr(alert, "recommended_actions", None))
        summary_markdown = NotificationService._format_diagnosis_markdown(getattr(alert, "ai_diagnosis_summary", None), max_items=3)

        if root_cause_markdown or recommended_actions_markdown or summary_markdown:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**AI 诊断**"}
            })
            if root_cause_markdown:
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🔍 根本原因**\n" + root_cause_markdown[:800]}})
            elif summary_markdown:
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**💬 诊断摘要**\n" + summary_markdown[:500]}})
            if recommended_actions_markdown:
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🛠 处置建议**\n" + recommended_actions_markdown[:800]}})

        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"[DBClaw 告警] {datasource.name if datasource else '未知'}"},
                    "template": color
                },
                "elements": elements
            }
        }

    @staticmethod
    async def _send_webhook(
        db: AsyncSession,
        alert: AlertMessage,
        webhook_url: str,
        subscription_id: int,
        datasource: Optional[Any] = None
    ) -> AlertDeliveryLog:
        """Send webhook notification"""
        log = AlertDeliveryLog(
            alert_id=alert.id,
            subscription_id=subscription_id,
            channel="webhook",
            recipient=webhook_url,
            status="pending"
        )
        db.add(log)

        try:
            async with aiohttp.ClientSession() as session:
                if NotificationService._is_feishu_webhook(webhook_url):
                    payload = NotificationService._build_feishu_payload(alert, datasource)
                elif NotificationService._is_dingtalk_webhook(webhook_url):
                    signed_url = NotificationService._build_dingtalk_url(webhook_url, None)
                    payload = NotificationService._build_dingtalk_payload(alert, datasource)
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with session.post(signed_url, json=payload, timeout=timeout) as response:
                        resp_text = await response.text()
                        if response.status not in [200, 201, 202]:
                            raise Exception(f"DingTalk webhook returned status {response.status}: {resp_text}")
                        resp_json = json.loads(resp_text)
                        if resp_json.get('errcode', 0) != 0:
                            raise Exception(f"DingTalk error {resp_json.get('errcode')}: {resp_json.get('errmsg')}")
                    log.status = "sent"
                    log.sent_at = now()
                    logger.info(f"DingTalk webhook sent to {webhook_url} for alert {alert.id}")
                    await db.commit()
                    await db.refresh(log)
                    return log
                else:
                    payload = {
                        "alert_id": alert.id,
                        "datasource_id": alert.datasource_id,
                        "alert_type": alert.alert_type,
                        "severity": alert.severity,
                        "title": alert.title,
                        "content": alert.content,
                        "metric_name": alert.metric_name,
                        "metric_value": alert.metric_value,
                        "threshold_value": alert.threshold_value,
                        "trigger_reason": alert.trigger_reason,
                        "created_at": alert.created_at.isoformat()
                    }
                    if datasource:
                        payload["datasource"] = {
                            "name": datasource.name,
                            "db_type": datasource.db_type,
                            "host": datasource.host,
                            "port": datasource.port,
                            "database": datasource.database
                        }
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.post(webhook_url, json=payload, timeout=timeout) as response:
                    resp_text = await response.text()
                    logger.debug(f"Feishu webhook response: status={response.status} body={resp_text}")
                    if response.status not in [200, 201, 202]:
                        raise Exception(f"Webhook returned status {response.status}: {resp_text}")
                    # Feishu returns error info in response body even on HTTP 200
                    if NotificationService._is_feishu_webhook(webhook_url):
                        resp_json = json.loads(resp_text)
                        if resp_json.get('code', 0) != 0:
                            raise Exception(f"Feishu error {resp_json.get('code')}: {resp_json.get('msg')}")

            log.status = "sent"
            log.sent_at = now()
            logger.info(f"Webhook sent to {webhook_url} for alert {alert.id}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"Failed to send webhook to {webhook_url}: {e}")

        await db.commit()
        await db.refresh(log)
        return log
