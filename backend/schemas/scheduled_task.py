"""Schemas for user-managed scheduled Python tasks."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.base import TimestampSerializerMixin


ScheduleType = Literal["interval", "cron"]
RunStatus = Literal["pending", "running", "success", "failed", "skipped"]
NotificationPolicy = Literal["never", "on_failure", "on_success", "always"]


class ScheduledTaskNotificationTarget(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)
    integration_id: int
    name: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True
    params: Dict[str, Any] = Field(default_factory=dict)


class ScheduledTaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    script_code: str = Field(..., min_length=1, description="Python 脚本内容，需定义 run(context)")
    schedule_type: ScheduleType = Field(..., description="调度类型：interval / cron")
    schedule_config: Dict[str, Any] = Field(..., description="调度配置")
    enabled: bool = Field(default=True, description="是否启用")
    timeout_seconds: int = Field(default=60, ge=1, le=3600, description="执行超时时间（秒）")
    max_concurrent_runs: int = Field(default=1, ge=1, le=10, description="最大并发运行数")
    notification_policy: NotificationPolicy = Field(default="never", description="运行结果通知策略")
    notification_targets: List[ScheduledTaskNotificationTarget] = Field(default_factory=list, description="出站通知目标配置")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("任务名称不能为空")
        return stripped


class ScheduledTaskCreate(ScheduledTaskBase):
    pass


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    script_code: Optional[str] = Field(None, min_length=1)
    schedule_type: Optional[ScheduleType] = None
    schedule_config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    timeout_seconds: Optional[int] = Field(None, ge=1, le=3600)
    max_concurrent_runs: Optional[int] = Field(None, ge=1, le=10)
    notification_policy: Optional[NotificationPolicy] = None
    notification_targets: Optional[List[ScheduledTaskNotificationTarget]] = None

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("任务名称不能为空")
        return stripped


class ScheduledTaskResponse(TimestampSerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    script_code: str
    schedule_type: str
    schedule_config: Dict[str, Any]
    enabled: bool
    timeout_seconds: int
    max_concurrent_runs: int
    notification_policy: str
    notification_targets: List[Dict[str, Any]]
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_status: Optional[str]
    last_error: Optional[str]
    created_by_id: Optional[int]
    updated_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class ScheduledTaskRunResponse(TimestampSerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    trigger_source: str
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    result: Optional[Dict[str, Any]]
    stdout: Optional[str]
    stderr: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
