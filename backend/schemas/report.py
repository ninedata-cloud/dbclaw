from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class ReportGenerateRequest(BaseModel):
    datasource_id: int
    report_type: str = "comprehensive"  # comprehensive, performance, security
    title: Optional[str] = None
    ai_enabled: bool = True  # Use AI analysis
    model_id: Optional[int] = None  # AI model to use
    kb_ids: Optional[List[int]] = None  # Knowledge bases to use


class ReportResponse(TimestampSerializerMixin, BaseModel):
    id: int
    datasource_id: int
    title: str
    report_type: str
    status: str
    summary: Optional[str] = None
    content_md: Optional[str] = None
    content_html: Optional[str] = None
    findings: Optional[Any] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    ai_model_id: Optional[int] = None
    kb_ids: Optional[List[int]] = None
    generation_method: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
