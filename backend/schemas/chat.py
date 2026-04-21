from pydantic import BaseModel
from typing import Optional, List, Any, Literal
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class SkillAuthorizationSettings(BaseModel):
    platform_operations: bool = False
    high_privilege_operations: bool = False
    knowledge_retrieval: bool = True


class ChatSessionCreate(BaseModel):
    datasource_id: Optional[int] = None
    host_id: Optional[int] = None
    title: Optional[str] = "New Session"
    ai_model_id: Optional[int] = None
    kb_ids: Optional[List[int]] = None
    disabled_tools: Optional[List[str]] = None
    skill_authorizations: Optional[SkillAuthorizationSettings] = None


class ChatSessionResponse(TimestampSerializerMixin, BaseModel):
    id: int
    datasource_id: Optional[int] = None
    host_id: Optional[int] = None
    ai_model_id: Optional[int] = None
    title: str
    kb_ids: Optional[List[int]] = None
    knowledge_snapshot: Optional[Any] = None
    disabled_tools: Optional[List[str]] = None
    skill_authorizations: Optional[SkillAuthorizationSettings] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatMessageResponse(TimestampSerializerMixin, BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    run_id: Optional[str] = None
    render_segments: Optional[Any] = None
    status: Optional[str] = None
    tool_calls: Optional[Any] = None
    attachments: Optional[List[Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    datasource_id: Optional[int] = None


class ChatApprovalResolveRequest(BaseModel):
    action: Literal["approved", "rejected"]
    comment: Optional[str] = None
