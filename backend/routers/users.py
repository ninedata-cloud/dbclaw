from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db
from backend.models.user import User
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.models.login_log import LoginLog
from backend.schemas.auth import (
    UserCreate, UserUpdate, UserResponse, ResetPasswordRequest, LoginLogResponse,
)
from datetime import datetime, timezone

from backend.utils.security import hash_password
from backend.dependencies import get_current_admin
from backend.services.session_service import SessionService

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=List[UserResponse])
async def list_user(db: AsyncSession = Depends(get_db)):
    result = await db.execute(alive_select(User).order_by(User.id))
    return result.scalars().all()


@router.post("", response_model=UserResponse)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username, alive_filter(User)))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        email=data.email,
        phone=data.phone,
        is_admin=data.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, data: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await get_alive_by_id(db, User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    user = await get_alive_by_id(db, User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.soft_delete(current_admin.id)
    user.session_version += 1
    await SessionService.revoke_user_session(db, user.id, "user_deleted")
    await db.commit()
    return {"message": "User deleted"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    user = await get_alive_by_id(db, User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin" and current_admin.id != user.id:
        raise HTTPException(status_code=403, detail="admin 密码只能由本人修改")

    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.session_version += 1
    await SessionService.revoke_user_session(db, user.id, "password_reset")
    await db.commit()
    return {"message": "Password reset successfully"}


@router.post("/{user_id}/toggle-status")
async def toggle_status(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own status")

    user = await get_alive_by_id(db, User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.is_active = not user.is_active
    if not user.is_active:
        user.session_version += 1
        await SessionService.revoke_user_session(db, user.id, "user_disabled")
    await db.commit()
    await db.refresh(user)
    return {"message": f"User {'enabled' if user.is_active else 'disabled'}", "is_active": user.is_active}


@router.get("/{user_id}/login-logs", response_model=List[LoginLogResponse])
async def get_login_log(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LoginLog)
        .where(LoginLog.user_id == user_id)
        .order_by(desc(LoginLog.logged_in_at))
        .limit(100)
    )
    return result.scalars().all()
