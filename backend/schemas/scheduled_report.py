"""
Pydantic schemas for scheduled reports
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ScheduledReportConfigCreate(BaseModel):
    """Schema for creating a scheduled report configuration"""
    datasource_id: int
    enabled: bool = True
    report_type: str = "comprehensive"
    use_ai_analysis: bool = False
    ai_model_id: Optional[int] = None
    kb_ids: Optional[List[int]] = None
    retention_days: int = 30


class ScheduledReportConfigUpdate(BaseModel):
    """Schema for updating a scheduled report configuration"""
    enabled: Optional[bool] = None
    report_type: Optional[str] = None
    use_ai_analysis: Optional[bool] = None
    ai_model_id: Optional[int] = None
    kb_ids: Optional[List[int]] = None
    retention_days: Optional[int] = None


class ScheduledReportConfigResponse(BaseModel):
    """Schema for scheduled report configuration response"""
    id: int
    datasource_id: int
    datasource_name: Optional[str] = None
    datasource_type: Optional[str] = None
    importance_level: Optional[str] = None
    enabled: bool
    report_type: str
    schedule_interval: int
    schedule_interval_display: str
    use_ai_analysis: bool
    ai_model_id: Optional[int] = None
    ai_model_name: Optional[str] = None
    kb_ids: Optional[List[int]] = None
    last_generated_at: Optional[datetime] = None
    next_scheduled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduledReportHistoryResponse(BaseModel):
    """Schema for scheduled report history response"""
    id: int
    config_id: int
    report_id: Optional[int] = None
    datasource_id: int
    datasource_name: Optional[str] = None
    scheduled_time: datetime
    actual_generation_time: Optional[datetime] = None
    generation_duration_seconds: Optional[float] = None
    status: str
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ScheduledReportStatsResponse(BaseModel):
    """Schema for scheduled report statistics"""
    total_configs: int
    enabled_configs: int
    total_reports_generated: int
    reports_today: int
    reports_this_week: int
    reports_this_month: int
    success_rate: float
    average_duration_seconds: Optional[float] = None
    failed_count: int
    skipped_count: int


class DatasourceScheduledReportStatsResponse(BaseModel):
    """Schema for datasource-specific scheduled report statistics"""
    datasource_id: int
    datasource_name: str
    total_reports: int
    successful_reports: int
    failed_reports: int
    skipped_reports: int
    success_rate: float
    average_duration_seconds: Optional[float] = None
    last_generated_at: Optional[datetime] = None
    next_scheduled_at: Optional[datetime] = None
