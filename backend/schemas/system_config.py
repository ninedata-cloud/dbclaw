from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime


class SystemConfigCreate(BaseModel):
    key: str
    value: str
    value_type: Literal["string", "integer", "float", "boolean", "json"]
    description: Optional[str] = None
    category: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    value_type: Optional[Literal["string", "integer", "float", "boolean", "json"]] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class SystemConfigResponse(BaseModel):
    id: int
    key: str
    value: str
    value_type: str
    description: Optional[str]
    category: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
