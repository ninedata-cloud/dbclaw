"""
统一外部集成管理 Pydantic Schema
"""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    integration_code: str = Field(
        ...,
        validation_alias=AliasChoices("integration_code", "integration_id"),
        serialization_alias="integration_id",
        description="唯一标识符",
    )
    name: str = Field(..., description="集成名称")
    description: Optional[str] = Field(None, description="描述")
    integration_type: str = Field(..., description="集成类型: outbound_notification / inbound_metric / bot")
    category: str = Field(default="custom", description="分类: webhook/email/sms/im/monitoring/custom")
    is_builtin: bool = Field(default=False, description="是否为内置模板")
    code: str = Field(..., description="可编程脚本")
    config_schema: Optional[Dict[str, Any]] = Field(None, description="参数 Schema (JSON Schema 格式)")
    enabled: bool = Field(default=True)


class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class IntegrationResponse(TimestampSerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    integration_code: str = Field(serialization_alias="integration_id")
    name: str
    description: Optional[str]
    integration_type: str
    category: str
    is_builtin: bool
    code: str
    config_schema: Optional[Dict[str, Any]]
    enabled: bool
    last_run_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime

class IntegrationTestResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[int] = None


class IntegrationBotBindingUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    params: Optional[Dict[str, Any]] = None


class IntegrationBotBindingResponse(TimestampSerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    integration_id: int
    code: str
    name: str
    enabled: bool
    params: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class IntegrationExecutionLogResponse(TimestampSerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    integration_id: int
    target_type: Optional[str]
    target_ref: Optional[str]
    subscription_id: Optional[int]
    datasource_id: Optional[int]
    target_name: Optional[str]
    params_snapshot: Optional[Dict[str, Any]]
    payload_summary: Optional[Dict[str, Any]]
    trigger_source: str
    trigger_ref_id: Optional[str]
    status: str
    execution_time_ms: Optional[int]
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime

class IntegrationTemplate(BaseModel):
    """内置集成模板信息"""
    template_id: str
    name: str
    description: str
    integration_type: str
    category: str
    config_schema: List[Dict[str, Any]]
    code_template: str
