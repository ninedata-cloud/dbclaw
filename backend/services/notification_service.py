from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from datetime import datetime, time as dt_time
import logging
import smtplib
import aiohttp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from backend.models.alert_message import AlertMessage
from backend.models.alert_subscription import AlertSubscription
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.models.user import User
from backend.models.system_config import SystemConfig

logger = logging.getLogger(__name__)


class NotificationService:
    """Notification dispatch service"""

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
        if subscription.datasource_ids:
            if alert.datasource_id not in subscription.datasource_ids:
                return False

        # Check severity filter
        if subscription.severity_levels:
            if alert.severity not in subscription.severity_levels:
                return False

        # Check time range filter
        if subscription.time_ranges:
            current_time = datetime.utcnow()
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

        Args:
            db: Database session
            alert: Alert to send
            subscription: Subscription configuration

        Returns:
            List of delivery log entries
        """
        # Get user information
        user_result = await db.execute(
            select(User).where(User.id == subscription.user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            logger.error(f"User {subscription.user_id} not found for subscription {subscription.id}")
            return []

        delivery_logs = []

        for channel in subscription.channels:
            if channel == "email" and user.email:
                log = await NotificationService._send_email(db, alert, user.email, subscription.id)
                delivery_logs.append(log)

            elif channel == "sms" and user.phone:
                log = await NotificationService._send_sms(db, alert, user.phone, subscription.id)
                delivery_logs.append(log)

            elif channel == "phone" and user.phone:
                log = await NotificationService._send_phone(db, alert, user.phone, subscription.id)
                delivery_logs.append(log)

            elif channel == "webhook" and subscription.webhook_url:
                log = await NotificationService._send_webhook(db, alert, subscription.webhook_url, subscription.id)
                delivery_logs.append(log)

        return delivery_logs

    @staticmethod
    async def _send_email(
        db: AsyncSession,
        alert: AlertMessage,
        recipient: str,
        subscription_id: int
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
            msg['Subject'] = f"[{alert.severity.upper()}] {alert.title}"

            body = f"""
Alert Details:
--------------
Severity: {alert.severity.upper()}
Datasource ID: {alert.datasource_id}
Alert Type: {alert.alert_type}

{alert.content}

Created at: {alert.created_at}
"""
            msg.attach(MIMEText(body, 'plain'))

            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_use_tls:
                    server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)

            log.status = "sent"
            log.sent_at = datetime.utcnow()
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
        subscription_id: int
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

                # Send via webhook
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "phone": recipient,
                        "message": f"[{alert.severity.upper()}] {alert.title}: {alert.content[:100]}"
                    }
                    async with session.post(webhook_url, json=payload) as response:
                        if response.status != 200:
                            raise Exception(f"Webhook returned status {response.status}")

            else:
                # Placeholder for Aliyun/Twilio integration
                raise NotImplementedError(f"SMS provider {sms_provider} not implemented")

            log.status = "sent"
            log.sent_at = datetime.utcnow()
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
        subscription_id: int
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

                # Send via webhook
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "phone": recipient,
                        "message": f"Alert: {alert.title}. Severity: {alert.severity}"
                    }
                    async with session.post(webhook_url, json=payload) as response:
                        if response.status != 200:
                            raise Exception(f"Webhook returned status {response.status}")

            else:
                # Placeholder for Aliyun/Twilio integration
                raise NotImplementedError(f"Phone provider {phone_provider} not implemented")

            log.status = "sent"
            log.sent_at = datetime.utcnow()
            logger.info(f"Phone call sent to {recipient} for alert {alert.id}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"Failed to send phone call to {recipient}: {e}")

        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def _send_webhook(
        db: AsyncSession,
        alert: AlertMessage,
        webhook_url: str,
        subscription_id: int
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
                async with session.post(webhook_url, json=payload, timeout=10) as response:
                    if response.status not in [200, 201, 202]:
                        raise Exception(f"Webhook returned status {response.status}")

            log.status = "sent"
            log.sent_at = datetime.utcnow()
            logger.info(f"Webhook sent to {webhook_url} for alert {alert.id}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            logger.error(f"Failed to send webhook to {webhook_url}: {e}")

        await db.commit()
        await db.refresh(log)
        return log
