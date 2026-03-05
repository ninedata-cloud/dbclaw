from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    db_type: str = Field(..., pattern="^(mysql|postgresql|mongodb|redis|sqlserver)$")
    host: str = Field(..., min_length=1)
    port: int = Field(..., gt=0, lt=65536)
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    ssh_host_id: Optional[int] = None
    extra_params: Optional[str] = None


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    ssh_host_id: Optional[int] = None
    extra_params: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    username: Optional[str] = None
    database: Optional[str] = None
    ssh_host_id: Optional[int] = None
    extra_params: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    version: Optional[str] = None
