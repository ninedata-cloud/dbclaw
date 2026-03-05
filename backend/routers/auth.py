from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models.user import User
from backend.models.login_log import LoginLog
from backend.schemas.auth import LoginRequest, LoginResponse, ChangePasswordRequest, UserResponse
from backend.utils.security import verify_password, hash_password, create_access_token
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    if not user or not verify_password(data.password, user.password_hash):
        # Log failed attempt
        log = LoginLog(
            user_id=user.id if user else 0,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        log = LoginLog(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Log successful login
    log = LoginLog(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
    )
    db.add(log)
    await db.commit()

    access_token = create_access_token(data={"sub": user.username})
    return LoginResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}
