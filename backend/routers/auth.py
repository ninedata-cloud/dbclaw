from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.database import get_db
from backend.models.user import User
from backend.models.login_log import LoginLog
from backend.models.soft_delete import alive_filter
from backend.schemas.auth import LoginRequest, LoginResponse, ChangePasswordRequest, CurrentUserUpdateRequest, UserResponse
from backend.utils.security import verify_password, hash_password
from backend.dependencies import get_current_user
from backend.services.session_service import SessionService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_idle_timeout_minutes * 60,
        path='/',
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path='/',
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
    )


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username, alive_filter(User)))
    user = result.scalar_one_or_none()

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    if not user or not verify_password(data.password, user.password_hash):
        log = LoginLog(
            user_id=user.id if user else 0,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        log = LoginLog(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=403, detail="账户已被禁用")

    log = LoginLog(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
    )
    db.add(log)

    session_id = await SessionService.create_session(
        db,
        user_id=user.id,
        session_version=user.session_version,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    _set_session_cookie(response, session_id)

    return LoginResponse(user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: CurrentUserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.display_name = data.display_name
    current_user.email = data.email
    current_user.phone = data.phone
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    session_id = request.cookies.get(get_settings().session_cookie_name)
    session = await SessionService.get_active_session(db, session_id)
    if session:
        await SessionService.revoke_session(db, session, "logout")
        await db.commit()
    _clear_session_cookie(response)
    return {"message": "Logged out"}


@router.post("/logout-all")
async def logout_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current_user.session_version += 1
    await SessionService.revoke_user_session(db, current_user.id, "logout_all")
    await db.commit()
    return {"message": "All sessions revoked"}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")

    current_user.password_hash = hash_password(data.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    current_user.session_version += 1
    await SessionService.revoke_user_session(db, current_user.id, "password_changed")
    await db.commit()
    _clear_session_cookie(response)
    return {"message": "Password changed successfully"}
