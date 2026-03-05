from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)
    display_name: Optional[str] = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    is_admin: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


class LoginLogResponse(BaseModel):
    id: int
    user_id: int
    login_time: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool

    class Config:
        from_attributes = True
