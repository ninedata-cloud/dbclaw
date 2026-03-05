from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SSHHostCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    host: str = Field(..., min_length=1)
    port: int = Field(22, gt=0, lt=65536)
    username: str = Field(..., min_length=1)
    auth_type: str = Field("password", pattern="^(password|key)$")
    password: Optional[str] = None
    private_key: Optional[str] = None


class SSHHostUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    auth_type: Optional[str] = None
    password: Optional[str] = None
    private_key: Optional[str] = None


class SSHHostResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str
    auth_type: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SSHTestResult(BaseModel):
    success: bool
    message: str
