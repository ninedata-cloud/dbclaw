from datetime import timedelta

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert_message import AlertMessage
from backend.models.report import Report
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.services.config_service import get_config
from backend.utils.security import create_public_share_token, decode_public_share_token


class PublicShareService:
    @staticmethod
    async def get_external_base_url(db: AsyncSession) -> str:
        value = await get_config(db, "app_external_base_url", default="")
        return (value or "").rstrip("/")

    @staticmethod
    def create_alert_share_token(alert_id: int, expires_minutes: int) -> str:
        return create_public_share_token(
            resource_type="alert",
            resource_id=alert_id,
            expires_delta=timedelta(minutes=expires_minutes),
        )

    @staticmethod
    def create_report_share_token(report_id: int, expires_minutes: int) -> str:
        return create_public_share_token(
            resource_type="report",
            resource_id=report_id,
            expires_delta=timedelta(minutes=expires_minutes),
        )

    @staticmethod
    def verify_alert_share_token(token: str, alert_id: int) -> None:
        try:
            decode_public_share_token(token, "alert", alert_id)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="分享链接无效或已过期"
            )

    @staticmethod
    def verify_report_share_token(token: str, report_id: int) -> None:
        try:
            decode_public_share_token(token, "report", report_id)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="分享链接无效或已过期"
            )

    @staticmethod
    async def get_report_by_alert_id(db: AsyncSession, alert_id: int) -> Report | None:
        result = await db.execute(
            select(Report).where(Report.alert_id == alert_id, alive_filter(Report)).order_by(Report.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_alert_or_404(db: AsyncSession, alert_id: int) -> AlertMessage:
        alert = await db.get(AlertMessage, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return alert

    @staticmethod
    async def get_report_or_404(db: AsyncSession, report_id: int) -> Report:
        report = await get_alive_by_id(db, Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
        return report
