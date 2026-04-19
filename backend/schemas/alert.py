from pydantic import BaseModel, Field, field_validator, model_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime


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


class AlertLinkedReport(BaseModel):
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
    diagnosis_refresh_needed: Optional[bool] = None
    diagnosis_trigger_reason: Optional[str] = None
    baseline_comparisons: List[AlertBaselineComparisonItem] = Field(default_factory=list)


class AlertMessageResponse(AlertMessageBase):
    id: int
    status: str
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    diagnosis_context: Optional[AlertDiagnosisContext] = None

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


class AlertSubscriptionResponse(BaseModel):
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

    class Config:
        from_attributes = True


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
    event_start_time: datetime
    event_end_time: datetime
    status: str
    severity: str
    title: str
    alert_type: Optional[str] = None
    metric_name: Optional[str] = None
    event_category: Optional[str] = None
    fault_domain: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    diagnosis_refresh_needed: Optional[bool] = None
    diagnosis_trigger_reason: Optional[str] = None
    ai_diagnosis_summary: Optional[str] = None
    root_cause: Optional[str] = None
    recommended_actions: Optional[str] = None
    diagnosis_status: Optional[str] = None


class AlertEventResponse(AlertEventBase):
    id: int
    first_alert_id: int
    latest_alert_id: int
    last_updated: datetime
    root_cause: Optional[str] = None
    recommended_actions: Optional[str] = None
    diagnosis_status: Optional[str] = None
    datasource_silence_until: Optional[datetime] = None
    datasource_silence_reason: Optional[str] = None

    @model_serializer
    def serialize_model(self):
        """Custom serializer to ensure UTC timezone in datetime fields"""
        from datetime import timezone
        data = {
            'id': self.id,
            'datasource_id': self.datasource_id,
            'aggregation_key': self.aggregation_key,
            'aggregation_type': self.aggregation_type,
            'alert_count': self.alert_count,
            'event_start_time': self.event_start_time.isoformat() if self.event_start_time else None,
            'event_end_time': self.event_end_time.isoformat() if self.event_end_time else None,
            'status': self.status,
            'severity': self.severity,
            'title': self.title,
            'alert_type': self.alert_type,
            'metric_name': self.metric_name,
            'event_category': self.event_category,
            'fault_domain': self.fault_domain,
            'lifecycle_stage': self.lifecycle_stage,
            'diagnosis_refresh_needed': self.diagnosis_refresh_needed,
            'diagnosis_trigger_reason': self.diagnosis_trigger_reason,
            'ai_diagnosis_summary': self.ai_diagnosis_summary,
            'root_cause': self.root_cause,
            'recommended_actions': self.recommended_actions,
            'diagnosis_status': self.diagnosis_status,
            'first_alert_id': self.first_alert_id,
            'latest_alert_id': self.latest_alert_id,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'datasource_silence_reason': self.datasource_silence_reason,
        }

        # Handle datasource_silence_until with UTC timezone
        if self.datasource_silence_until:
            dt = self.datasource_silence_until
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            data['datasource_silence_until'] = dt.isoformat()
        else:
            data['datasource_silence_until'] = None

        return data

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
    user_id: Optional[int] = None
