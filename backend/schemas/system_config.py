from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class SystemConfigCreate(BaseModel):
    key: str
    value: str
    value_type: Literal["string", "integer", "float", "boolean", "json"]
    description: Optional[str] = None
    category: Optional[str] = None
    is_encrypted: bool = False


class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    value_type: Optional[Literal["string", "integer", "float", "boolean", "json"]] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    is_encrypted: Optional[bool] = None


class SystemConfigResponse(TimestampSerializerMixin, BaseModel):
    id: int
    key: str
    value: Optional[str]
    value_type: str
    description: Optional[str]
    category: Optional[str]
    is_active: bool
    is_encrypted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
