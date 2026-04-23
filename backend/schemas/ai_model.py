from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin

AIModelProvider = Literal["openai", "dashscope", "anthropic", "other"]
AIModelProtocol = Literal["openai", "anthropic"]
AIModelReasoningEffort = Literal["low", "medium", "high"]


class AIModelCreate(BaseModel):
    name: str
    provider: AIModelProvider
    protocol: AIModelProtocol = "openai"
    api_key: str
    base_url: str
    model_name: str
    context_window: Optional[int] = Field(default=None, ge=1)
    reasoning_effort: Optional[AIModelReasoningEffort] = None


class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[AIModelProvider] = None
    protocol: Optional[AIModelProtocol] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    context_window: Optional[int] = Field(default=None, ge=1)
    reasoning_effort: Optional[AIModelReasoningEffort] = None


class AIModelResponse(TimestampSerializerMixin, BaseModel):
    id: int
    name: str
    provider: AIModelProvider
    protocol: AIModelProtocol
    api_key_masked: str
    base_url: str
    model_name: str
    context_window: Optional[int] = None
    reasoning_effort: Optional[AIModelReasoningEffort] = None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AIModelTestMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=4000)


class AIModelTestChatRequest(BaseModel):
    messages: list[AIModelTestMessage] = Field(min_length=1, max_length=20)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=4096)


class AIModelTestChatResponse(BaseModel):
    success: bool = True
    reply: str
    model: str
    provider: AIModelProvider
    latency_ms: int
