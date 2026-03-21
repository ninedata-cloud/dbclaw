"""
统一外部集成管理 Pydantic Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class IntegrationCreate(BaseModel):
    integration_id: str = Field(..., description="唯一标识符")
    name: str = Field(..., description="集成名称")
    description: Optional[str] = Field(None, description="描述")
    integration_type: str = Field(..., description="集成类型: outbound_notification / inbound_metric")
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


class IntegrationResponse(BaseModel):
    id: int
    integration_id: str
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

    class Config:
        from_attributes = True


class AlertChannelCreate(BaseModel):
    name: str = Field(..., description="渠道名称")
    description: Optional[str] = None
    integration_id: int = Field(..., description="引用的集成 ID")
    params: Dict[str, Any] = Field(default_factory=dict, description="渠道参数")
    enabled: bool = Field(default=True)


class AlertChannelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class AlertChannelResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    integration_id: int
    params: Dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    # 冗余字段，方便前端展示
    integration_name: Optional[str] = None
    integration_type: Optional[str] = None
    integration_category: Optional[str] = None

    class Config:
        from_attributes = True


class IntegrationTestResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[int] = None


class IntegrationExecutionLogResponse(BaseModel):
    id: int
    integration_id: int
    channel_id: Optional[int]
    trigger_source: str
    trigger_ref_id: Optional[str]
    status: str
    execution_time_ms: Optional[int]
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IntegrationTemplate(BaseModel):
    """内置集成模板信息"""
    template_id: str
    name: str
    description: str
    integration_type: str
    category: str
    config_schema: List[Dict[str, Any]]  # 配置项描述
    code_template: str
