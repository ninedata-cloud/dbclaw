from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# Alert Message Schemas
class AlertMessageBase(BaseModel):
    datasource_id: int
    alert_type: str = Field(..., pattern="^(threshold_violation|custom_expression|system_error)$")
    severity: str = Field(..., pattern="^(critical|high|medium|low)$")
    title: str = Field(..., max_length=255)
    content: str
    metric_name: Optional[str] = Field(None, max_length=100)
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None
    trigger_reason: Optional[str] = None


class AlertMessageCreate(AlertMessageBase):
    pass


class AlertMessageUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(active|acknowledged|resolved)$")
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class AlertMessageResponse(AlertMessageBase):
    id: int
    status: str
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Alert Subscription Schemas
class TimeRange(BaseModel):
    start: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")  # HH:MM format
    end: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    days: List[int] = Field(..., min_length=1, max_length=7)  # 0=Monday, 6=Sunday

    @field_validator('days')
    @classmethod
    def validate_days(cls, v):
        if not all(0 <= day <= 6 for day in v):
            raise ValueError('Days must be between 0 (Monday) and 6 (Sunday)')
        return v


class AlertSubscriptionBase(BaseModel):
    datasource_ids: List[int] = Field(default_factory=list)  # empty = all
    severity_levels: List[str] = Field(default_factory=list)  # empty = all
    time_ranges: List[TimeRange] = Field(default_factory=list)  # empty = 24/7
    channels: List[str] = Field(..., min_length=1)  # at least one channel required
    webhook_url: Optional[str] = Field(None, max_length=500)
    enabled: bool = True
    aggregation_script: Optional[str] = None

    @field_validator('severity_levels')
    @classmethod
    def validate_severity_levels(cls, v):
        valid_severities = {'critical', 'high', 'medium', 'low'}
        if v and not all(s in valid_severities for s in v):
            raise ValueError(f'Severity levels must be one of: {valid_severities}')
        return v

    @field_validator('channels')
    @classmethod
    def validate_channels(cls, v):
        valid_channels = {'email', 'sms', 'phone', 'webhook'}
        if not all(c in valid_channels for c in v):
            raise ValueError(f'Channels must be one of: {valid_channels}')
        return v


class AlertSubscriptionCreate(AlertSubscriptionBase):
    user_id: int


class AlertSubscriptionUpdate(BaseModel):
    datasource_ids: Optional[List[int]] = None
    severity_levels: Optional[List[str]] = None
    time_ranges: Optional[List[TimeRange]] = None
    channels: Optional[List[str]] = None
    webhook_url: Optional[str] = None
    enabled: Optional[bool] = None
    aggregation_script: Optional[str] = None


class AlertSubscriptionResponse(AlertSubscriptionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Alert Delivery Log Schemas
class AlertDeliveryLogBase(BaseModel):
    alert_id: int
    subscription_id: int
    channel: str = Field(..., pattern="^(email|sms|phone|webhook)$")
    recipient: str = Field(..., max_length=255)
    status: str = Field(default="pending", pattern="^(pending|sent|failed)$")
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None


class AlertDeliveryLogCreate(AlertDeliveryLogBase):
    pass


class AlertDeliveryLogResponse(AlertDeliveryLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Query Schemas
class AlertQueryParams(BaseModel):
    datasource_ids: Optional[List[int]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|acknowledged|resolved|all)$")
    search: Optional[str] = None
    severity: Optional[str] = Field(None, pattern="^(critical|high|medium|low)$")
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AlertAcknowledgeRequest(BaseModel):
    user_id: int


class AlertResolveRequest(BaseModel):
    pass


class TestNotificationRequest(BaseModel):
    subscription_id: int


# Alert Event Schemas
class AlertEventBase(BaseModel):
    datasource_id: int
    aggregation_key: str
    aggregation_type: str
    alert_count: int
    event_start_time: datetime
    event_end_time: datetime
    status: str
    severity: str
    title: str
    alert_type: Optional[str] = None
    metric_name: Optional[str] = None


class AlertEventResponse(AlertEventBase):
    id: int
    first_alert_id: int
    latest_alert_id: int
    last_updated: datetime

    class Config:
        from_attributes = True


class AlertEventQueryParams(BaseModel):
    datasource_ids: Optional[List[int]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|acknowledged|resolved|all)$")
    severity: Optional[str] = Field(None, pattern="^(critical|high|medium|low)$")
    search: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AlertEventAcknowledgeRequest(BaseModel):
    user_id: int

