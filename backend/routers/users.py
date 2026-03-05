from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db
from backend.models.user import User
from backend.models.login_log import LoginLog
from backend.schemas.auth import (
    UserCreate, UserUpdate, UserResponse, ResetPasswordRequest, LoginLogResponse,
)
from backend.utils.security import hash_password
from backend.dependencies import get_current_admin

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=List[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("", response_model=UserResponse)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        is_admin=data.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, data: UserUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()
    return {"message": "User deleted"}


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: int, data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(data.new_password)
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

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active
    await db.commit()
    await db.refresh(user)
    return {"message": f"User {'enabled' if user.is_active else 'disabled'}", "is_active": user.is_active}


@router.get("/{user_id}/login-logs", response_model=List[LoginLogResponse])
async def get_login_logs(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LoginLog)
        .where(LoginLog.user_id == user_id)
        .order_by(desc(LoginLog.login_time))
        .limit(100)
    )
    return result.scalars().all()
