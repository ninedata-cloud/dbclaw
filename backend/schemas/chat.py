from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ChatSessionCreate(BaseModel):
    datasource_id: Optional[int] = None
    title: Optional[str] = "New Session"
    ai_model_id: Optional[int] = None
    kb_ids: Optional[List[int]] = None
    disabled_tools: Optional[List[str]] = None


class ChatSessionResponse(BaseModel):
    id: int
    datasource_id: Optional[int] = None
    ai_model_id: Optional[int] = None
    title: str
    kb_ids: Optional[List[int]] = None
    disabled_tools: Optional[List[str]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
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
    attachments: Optional[List[Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    datasource_id: Optional[int] = None
