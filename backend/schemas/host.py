from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class HostCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    host: str = Field(..., min_length=1)
    port: int = Field(22, gt=0, lt=65536)
    username: str = Field(..., min_length=1)
    auth_type: str = Field("password", pattern="^(password|key|agent)$")
    password: Optional[str] = None
    private_key: Optional[str] = None


class HostUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    auth_type: Optional[str] = None
    password: Optional[str] = None
    private_key: Optional[str] = None


class HostResponse(TimestampSerializerMixin, BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str
    auth_type: str
    os_version: Optional[str] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    status: str = "unknown"  # normal, warning, error, offline
    status_message: Optional[str] = None
    last_check_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SSHTestResult(BaseModel):
    success: bool
    message: str
