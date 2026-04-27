from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.database import get_db
from backend.models.user import User
from backend.models.soft_delete import alive_filter
from backend.services.session_service import SessionService


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    settings = get_settings()
    raw_session_id = request.cookies.get(settings.session_cookie_name)
    session = await SessionService.get_active_session(db, raw_session_id)
    if session:
        result = await db.execute(select(User).where(User.id == session.user_id, alive_filter(User)))
        user = result.scalar_one_or_none()
        if user is None:
            await SessionService.revoke_session(db, session, "user_not_found")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if not user.is_active:
            await SessionService.revoke_session(db, session, "user_disabled")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
        if session.session_version != user.session_version:
            await SessionService.revoke_session(db, session, "session_version_mismatch")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        if session.id and session.status == "active":
            await SessionService.touch_session(db, session)
            await db.commit()
        return user

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user
