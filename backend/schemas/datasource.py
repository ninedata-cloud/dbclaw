from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DatasourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    db_type: str = Field(..., pattern="^(mysql|postgresql|mongodb|redis|sqlserver|oracle|tidb|oceanbase|opengauss|dm)$")
    host: str = Field(..., min_length=1)
    port: int = Field(..., gt=0, lt=65536)
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    host_id: Optional[int] = None
    extra_params: Optional[str] = None
    importance_level: Optional[str] = Field(default='production', pattern="^(core|production|development|temporary)$")
    monitoring_interval: Optional[int] = Field(default=60, ge=5, le=3600)


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    host_id: Optional[int] = None
    extra_params: Optional[str] = None
    importance_level: Optional[str] = Field(None, pattern="^(core|production|development|temporary)$")
    monitoring_interval: Optional[int] = Field(None, ge=5, le=3600)


class DatasourceResponse(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    username: Optional[str] = None
    database: Optional[str] = None
    host_id: Optional[int] = None
    extra_params: Optional[str] = None
    is_active: bool = True
    importance_level: str = 'production'
    monitoring_interval: int = 60
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DatasourceTestResult(BaseModel):
    success: bool
    message: str
    version: Optional[str] = None
