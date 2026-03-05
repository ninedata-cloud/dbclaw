from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ChatSessionCreate(BaseModel):
    connection_id: Optional[int] = None
    title: Optional[str] = "New Session"


class ChatSessionResponse(BaseModel):
    id: int
    connection_id: Optional[int] = None
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    tool_calls: Optional[Any] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    connection_id: Optional[int] = None
