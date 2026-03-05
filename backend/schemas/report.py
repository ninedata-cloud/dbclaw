from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ReportGenerateRequest(BaseModel):
    connection_id: int
    report_type: str = "comprehensive"  # comprehensive, performance, security
    title: Optional[str] = None


class ReportResponse(BaseModel):
    id: int
    connection_id: int
    title: str
    report_type: str
    status: str
    summary: Optional[str] = None
    findings: Optional[Any] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
