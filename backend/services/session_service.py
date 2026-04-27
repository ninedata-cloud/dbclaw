from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.user_session import UserSession
from backend.utils.security import generate_session_id, hash_session_id


class SessionService:
    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def build_expiry() -> datetime:
        settings = get_settings()
        return SessionService._utc_now() + timedelta(minutes=settings.session_idle_timeout_minutes)

    @staticmethod
    async def create_session(
        db: AsyncSession,
        *,
        user_id: int,
        session_version: int,
        ip_address: str | None,
        user_agent: str | None,
    ) -> str:
        raw_session_id = generate_session_id()
        session = UserSession(
            user_id=user_id,
            session_id_hash=hash_session_id(raw_session_id),
            session_version=session_version,
            status="active",
            expires_at=SessionService.build_expiry(),
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500] or None,
        )
        db.add(session)
        await db.flush()
        return raw_session_id

    @staticmethod
    async def get_active_session(db: AsyncSession, raw_session_id: str | None) -> UserSession | None:
        if not raw_session_id:
            return None
        result = await db.execute(
            select(UserSession).where(UserSession.session_id_hash == hash_session_id(raw_session_id))
        )
        session = result.scalar_one_or_none()
        if not session or session.status != "active":
            return None
        expires_at = SessionService._as_utc(session.expires_at)
        if expires_at <= SessionService._utc_now():
            session.status = "expired"
            session.revoked_at = SessionService._utc_now()
            session.revoked_reason = "expired"
            await db.commit()
            return None
        session.expires_at = expires_at
        return session

    @staticmethod
    async def touch_session(db: AsyncSession, session: UserSession) -> None:
        session.last_seen_at = SessionService._utc_now()
        session.expires_at = SessionService.build_expiry()
        await db.flush()

    @staticmethod
    async def revoke_session(db: AsyncSession, session: UserSession, reason: str) -> None:
        session.status = "revoked"
        session.revoked_at = SessionService._utc_now()
        session.revoked_reason = reason
        await db.flush()

    @staticmethod
    async def revoke_user_session(db: AsyncSession, user_id: int, reason: str) -> None:
        now = SessionService._utc_now()
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.status == "active")
            .values(status="revoked", revoked_at=now, revoked_reason=reason)
        )
        await db.flush()
