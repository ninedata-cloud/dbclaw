from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class DatasourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    db_type: str = Field(..., pattern="^(mysql|postgresql|sqlserver|oracle|tdsql-c-mysql|opengauss|hana)$")
    host: str = Field(..., min_length=1)
    port: int = Field(..., gt=0, lt=65536)
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    host_id: Optional[int] = None
    extra_params: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    importance_level: Optional[str] = Field(default='production', pattern="^(core|production|development|temporary)$")
    remark: Optional[str] = Field(None, description="备注，帮助 AI 诊断时理解数据源背景")

    # 监控数据来源配置
    metric_source: Optional[Literal['system', 'integration']] = Field(default='system', description="监控数据来源")
    external_instance_id: Optional[str] = Field(None, description="外部系统实例 ID")
    inbound_source: Optional[Dict[str, Any]] = Field(None, description="入站集成配置")


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    host_id: Optional[int] = None
    extra_params: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    importance_level: Optional[str] = Field(None, pattern="^(core|production|development|temporary)$")
    remark: Optional[str] = Field(None, description="备注，帮助 AI 诊断时理解数据源背景")

    # 监控数据来源配置
    metric_source: Optional[Literal['system', 'integration']] = None
    external_instance_id: Optional[str] = None
    inbound_source: Optional[Dict[str, Any]] = None


class DatasourceResponse(TimestampSerializerMixin, BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    username: Optional[str] = None
    database: Optional[str] = None
    host_id: Optional[int] = None
    extra_params: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True
    importance_level: str = 'production'
    remark: Optional[str] = None

    # 监控数据来源配置
    metric_source: str = 'system'
    external_instance_id: Optional[str] = None
    inbound_source: Optional[Dict[str, Any]] = None

    # 临时静默配置
    silence_until: Optional[datetime] = None
    silence_reason: Optional[str] = None

    # 版本信息
    db_version: Optional[str] = None

    # 连接状态
    connection_status: str = 'unknown'
    connection_error: Optional[str] = None
    connection_checked_at: Optional[datetime] = None

    # 最新指标数据
    cpu_usage: Optional[float] = None
    qps: Optional[float] = None
    connections_active: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DatasourceTestRequest(BaseModel):
    datasource_id: Optional[int] = None  # If provided, use saved password when password is None
    db_type: str = Field(..., pattern="^(mysql|postgresql|sqlserver|oracle|tdsql-c-mysql|opengauss|hana)$")
    host: str = Field(..., min_length=1)
    port: int = Field(..., gt=0, lt=65536)
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


class DatasourceDiagnosticClassification(BaseModel):
    layer: str
    category: str
    code: str
    severity: str = 'error'
    retryable: bool = False


class DatasourceDiagnosticCheck(BaseModel):
    layer: str
    name: str
    success: bool
    details: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    skipped: bool = False
    reason: Optional[str] = None


class DatasourceDiagnosticHints(BaseModel):
    probable_causes: List[str] = []
    recommendations: List[str] = []


class DatasourceTestResult(BaseModel):
    success: bool
    message: str
    version: Optional[str] = None
    summary: Optional[str] = None
    classification: Optional[DatasourceDiagnosticClassification] = None
    checks: List[DatasourceDiagnosticCheck] = []
    diagnosis: Optional[DatasourceDiagnosticHints] = None
    raw_error: Optional[str] = None
    target: Optional[Dict[str, Any]] = None
    timing: Optional[Dict[str, Any]] = None


class DatasourceSilenceRequest(BaseModel):
    """设置数据源静默的请求"""
    hours: float = Field(..., ge=0.5, le=240, description="静默时长（小时），范围 0.5-240")
    reason: Optional[str] = Field(None, max_length=500, description="静默原因")


class DatasourceSilenceResponse(TimestampSerializerMixin, BaseModel):
    """数据源静默状态响应"""
    datasource_id: int
    silence_until: Optional[datetime] = None
    silence_reason: Optional[str] = None
    is_silenced: bool = False
    remaining_hours: Optional[float] = None  # 剩余静默时长（小时）

    class Config:
        from_attributes = True
