from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AIModelCreate(BaseModel):
    name: str
    provider: str
    api_key: str
    base_url: str
    model_name: str


class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None


class AIModelResponse(BaseModel):
    id: int
    name: str
    provider: str
    api_key_masked: str
    base_url: str
    model_name: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
