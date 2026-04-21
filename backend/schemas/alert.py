from pydantic import BaseModel, Field, field_validator, model_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime

from backend.schemas.base import BaseSchema


# Alert Message Schemas
class AlertMessageBase(BaseModel):
    datasource_id: int
    alert_type: str = Field(..., pattern="^(threshold_violation|baseline_deviation|custom_expression|system_error|ai_policy_violation)$")
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


class AlertLinkedReport(BaseSchema):
    report_id: int
    title: str
    status: str
    trigger_type: Optional[str] = None
    created_at: datetime
    summary: Optional[str] = None


class AlertDatasourceInfo(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database: Optional[str] = None
    importance_level: str
    remark: Optional[str] = None
    connection_status: str
    connection_error: Optional[str] = None


class AlertBaselineComparisonItem(BaseModel):
    metric_name: str
    current_value: Optional[float] = None
    baseline_avg: Optional[float] = None
    baseline_p95: Optional[float] = None
    upper_bound: Optional[float] = None
    deviation_ratio: Optional[float] = None
    sample_count: int = 0
    status: str = "unknown"
    slot_label: Optional[str] = None


class AlertDiagnosisContext(BaseModel):
    datasource_name: Optional[str] = None
    datasource_type: Optional[str] = None
    datasource_info: Optional[AlertDatasourceInfo] = None
    case_summary: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    root_cause: Optional[str] = None
    recommended_action: Optional[str] = None
    latest_trigger_type: Optional[str] = None
    linked_report: Optional[AlertLinkedReport] = None
    diagnosis_entry_hash: Optional[str] = None
    event_category: Optional[str] = None
    fault_domain: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    is_diagnosis_refresh_needed: Optional[bool] = None
    diagnosis_trigger_reason: Optional[str] = None
    baseline_comparisons: List[AlertBaselineComparisonItem] = Field(default_factory=list)


class AlertMessageResponse(AlertMessageBase, BaseSchema):
    id: int
    status: str
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    diagnosis_context: Optional[AlertDiagnosisContext] = None


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


class IntegrationTarget(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)
    integration_id: int
    name: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True
    notify_on: List[str] = Field(default_factory=lambda: ["alert", "recovery"], min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


class AlertSubscriptionBase(BaseModel):
    datasource_ids: List[int] = Field(default_factory=list)  # empty = all
    severity_levels: List[str] = Field(default_factory=list)  # empty = all
    time_ranges: List[TimeRange] = Field(default_factory=list)  # empty = 24/7
    integration_targets: List[IntegrationTarget] = Field(..., min_length=1)
    enabled: bool = True
    aggregation_script: Optional[str] = None

    @field_validator('severity_levels')
    @classmethod
    def validate_severity_levels(cls, v):
        valid_severities = {'critical', 'high', 'medium', 'low'}
        if v and not all(s in valid_severities for s in v):
            raise ValueError(f'Severity levels must be one of: {valid_severities}')
        return v


class AlertSubscriptionCreate(AlertSubscriptionBase):
    user_id: Optional[int] = None


class AlertSubscriptionUpdate(BaseModel):
    datasource_ids: Optional[List[int]] = None
    severity_levels: Optional[List[str]] = None
    time_ranges: Optional[List[TimeRange]] = None
    integration_targets: Optional[List[IntegrationTarget]] = None
    enabled: Optional[bool] = None
    aggregation_script: Optional[str] = None


class AlertSubscriptionResponse(BaseSchema):
    id: int
    user_id: int
    datasource_ids: List[int] = Field(default_factory=list)
    severity_levels: List[str] = Field(default_factory=list)
    time_ranges: List[TimeRange] = Field(default_factory=list)
    integration_targets: List[IntegrationTarget] = Field(default_factory=list)
    enabled: bool = True
    aggregation_script: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# Alert Delivery Log Schemas
class AlertDeliveryLogBase(BaseModel):
    alert_id: int
    subscription_id: int
    integration_id: Optional[int] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    channel: str = Field(..., max_length=100)
    recipient: str = Field(..., max_length=255)
    status: str = Field(default="pending", pattern="^(pending|sent|failed)$")
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None


class AlertDeliveryLogCreate(AlertDeliveryLogBase):
    pass


class AlertDeliveryLogResponse(AlertDeliveryLogBase, BaseSchema):
    id: int
    created_at: datetime


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
    user_id: Optional[int] = None


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
    event_started_at: datetime
    event_ended_at: datetime
    status: str
    severity: str
    title: str
    alert_type: Optional[str] = None
    metric_name: Optional[str] = None
    event_category: Optional[str] = None
    fault_domain: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    is_diagnosis_refresh_needed: Optional[bool] = None
    diagnosis_trigger_reason: Optional[str] = None
    ai_diagnosis_summary: Optional[str] = None
    root_cause: Optional[str] = None
    recommended_actions: Optional[str] = None
    diagnosis_status: Optional[str] = None


class AlertEventResponse(AlertEventBase, BaseSchema):
    id: int
    first_alert_id: int
    latest_alert_id: int
    updated_at: datetime
    root_cause: Optional[str] = None
    recommended_actions: Optional[str] = None
    diagnosis_status: Optional[str] = None
    datasource_silence_until: Optional[datetime] = None
    datasource_silence_reason: Optional[str] = None


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
    user_id: Optional[int] = None
