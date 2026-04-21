from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.schemas.datasource import DatasourceResponse
from backend.schemas.base import TimestampSerializerMixin


class InstanceCapabilities(BaseModel):
    supports_variables: bool = True
    supports_sessions: bool = True
    supports_terminate_session: bool = False
    supports_os_metrics: bool = False


class InstanceInspectionSummary(TimestampSerializerMixin, BaseModel):
    enabled: bool = False
    schedule_interval: Optional[int] = None
    next_scheduled_at: Optional[datetime] = None
    last_report_id: Optional[int] = None
    last_report_title: Optional[str] = None
    last_report_status: Optional[str] = None
    last_report_created_at: Optional[datetime] = None


class InstanceSummaryResponse(TimestampSerializerMixin, BaseModel):
    datasource: DatasourceResponse
    latest_metric: Optional[Dict[str, Any]] = None
    metric_collected_at: Optional[datetime] = None
    health: Dict[str, Any] = Field(default_factory=dict)
    active_alert_event_count: int = 0
    active_alert_count: int = 0
    inspection: InstanceInspectionSummary = Field(default_factory=InstanceInspectionSummary)
    capabilities: InstanceCapabilities = Field(default_factory=InstanceCapabilities)


class InstanceVariableItem(BaseModel):
    key: str
    value: str
    category: str = "general"
    raw: Any = None


class InstanceSessionItem(BaseModel):
    session_id: str
    user: Optional[str] = None
    database: Optional[str] = None
    client: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[int] = None
    wait_event: Optional[str] = None
    sql_text: Optional[str] = None
    can_terminate: bool = False
    raw: Dict[str, Any] = Field(default_factory=dict)


class TerminateSessionResponse(BaseModel):
    success: bool = True
    session_id: str
    message: str
    datasource_id: int
    db_type: str
    result: Optional[Dict[str, Any]] = None


class InstanceTrafficHistoryPoint(TimestampSerializerMixin, BaseModel):
    timestamp: datetime
    rx_rate: Optional[float] = None
    tx_rate: Optional[float] = None
    total_rate: Optional[float] = None
    mode: str = "measured"


class InstanceTrafficClientItem(BaseModel):
    client_id: str
    client_label: str
    session_count: int = 0
    active_session_count: int = 0
    waiting_session_count: int = 0
    idle_session_count: int = 0
    user_count: int = 0
    user: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    max_duration_seconds: Optional[int] = None
    sample_sql: Optional[str] = None
    sql_samples: List[str] = Field(default_factory=list)
    heat_score: float = 0
    status: str = "idle"
    estimated_rx_rate: Optional[float] = None
    estimated_tx_rate: Optional[float] = None
    estimated_total_rate: Optional[float] = None


class InstanceTrafficSnapshotResponse(TimestampSerializerMixin, BaseModel):
    datasource: DatasourceResponse
    captured_at: datetime
    poll_interval_seconds: int = 5
    rate_mode: str = "unavailable"
    rate_label: str = "暂无实时网络字节指标"
    total_client_count: int = 0
    total_session_count: int = 0
    active_session_count: int = 0
    waiting_session_count: int = 0
    idle_session_count: int = 0
    max_session_count: Optional[int] = None
    total_rx_rate: Optional[float] = None
    total_tx_rate: Optional[float] = None
    total_rate: Optional[float] = None
    clients: List[InstanceTrafficClientItem] = Field(default_factory=list)
    history: List[InstanceTrafficHistoryPoint] = Field(default_factory=list)
