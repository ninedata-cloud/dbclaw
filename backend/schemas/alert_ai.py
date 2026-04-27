from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator
from backend.schemas.base import TimestampSerializerMixin


class AlertAIPolicyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    rule_text: str = Field(..., min_length=1)
    enabled: bool = True
    model_id: Optional[int] = None
    analysis_strategy: str = Field(default="candidate_only", pattern="^(candidate_only)$")
    analysis_config: Dict[str, Any] = Field(default_factory=dict)


class AlertAIPolicyCreate(AlertAIPolicyBase):
    pass


class AlertAIPolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    rule_text: Optional[str] = Field(None, min_length=1)
    enabled: Optional[bool] = None
    model_id: Optional[int] = None
    analysis_strategy: Optional[str] = Field(None, pattern="^(candidate_only)$")
    analysis_config: Optional[Dict[str, Any]] = None


class AlertAIPolicyResponse(TimestampSerializerMixin, AlertAIPolicyBase):
    id: int
    compiled_trigger_profile: Optional[Dict[str, Any]] = None
    compile_status: str = "pending"
    compile_error: Optional[str] = None
    compiled_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertAIPolicyToggleRequest(BaseModel):
    enabled: bool


class AlertAIEvaluationLogResponse(TimestampSerializerMixin, BaseModel):
    id: int
    datasource_id: int
    datasource_name: Optional[str] = None
    policy_id: Optional[int] = None
    policy_source: str
    policy_fingerprint: str
    model_id: Optional[int] = None
    mode: str
    decision: Optional[str] = None
    confidence: Optional[float] = None
    severity: Optional[str] = None
    policy_severity_hint: Optional[str] = None
    severity_source: Optional[str] = None
    trigger_inspection: bool = False
    accepted: bool = False
    error_message: Optional[str] = None
    reason: Optional[str] = None
    evidence: Optional[List[str]] = None
    feature_summary: Optional[Dict[str, Any]] = None
    raw_response: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertAIStatsResponse(BaseModel):
    samples_seen: int = 0
    candidate_hits: int = 0
    ai_evaluations: int = 0
    gate_skips_by_reason: Dict[str, int] = Field(default_factory=dict)
    token_saved_estimate: int = 0
    avg_tokens_per_evaluation: int = 0


class AlertAIPreviewRequest(BaseModel):
    datasource_id: int
    ai_policy_source: str = Field(default="inline", pattern="^(inline|template)$")
    ai_policy_text: Optional[str] = None
    ai_policy_id: Optional[int] = None
    alert_ai_model_id: Optional[int] = None
    hours: int = Field(default=24, ge=1, le=72)
    max_samples: int = Field(default=12, ge=1, le=24)

    @model_validator(mode="after")
    def validate_policy_source(self):
        if self.ai_policy_source == "template" and not self.ai_policy_id:
            raise ValueError("选择模板时必须提供 ai_policy_id")
        if self.ai_policy_source == "inline" and not (self.ai_policy_text or "").strip():
            raise ValueError("直接输入规则时必须提供 ai_policy_text")
        return self


class AlertAIPreviewSample(TimestampSerializerMixin, BaseModel):
    snapshot_id: int
    collected_at: datetime
    decision: str
    confidence: float
    severity: str
    policy_severity_hint: Optional[str] = None
    severity_source: str = "inferred"
    reason: str
    evidence: List[str] = Field(default_factory=list)
    accepted: bool = False
    action: str = "noop"


class AlertAIPreviewResponse(BaseModel):
    datasource_id: int
    policy_source: str
    policy_name: str
    model_id: Optional[int] = None
    sample_count: int
    alert_count: int = 0
    recover_count: int = 0
    samples: List[AlertAIPreviewSample] = Field(default_factory=list)
