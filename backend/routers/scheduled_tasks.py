"""Scheduled task management API."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.schemas.scheduled_task import (
    ScheduledTaskCreate,
    ScheduledTaskResponse,
    ScheduledTaskRunResponse,
    ScheduledTaskUpdate,
)
from backend.services.scheduled_task_service import ScheduledTaskService
from backend.i18n.locale import message_payload
from backend.i18n.errors import ApiError

router = APIRouter(prefix="/api", tags=["scheduled-tasks"])


@router.get("/scheduled-tasks", response_model=List[ScheduledTaskResponse])
async def list_scheduled_tasks(
    keyword: Optional[str] = Query(None, description="名称/描述关键词"),
    enabled: Optional[bool] = Query(None, description="启用状态"),
    last_status: Optional[str] = Query(None, description="最近运行状态"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ScheduledTaskService.list_tasks(db, keyword=keyword, enabled=enabled, last_status=last_status)


@router.post("/scheduled-tasks", response_model=ScheduledTaskResponse)
async def create_scheduled_task(
    data: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await ScheduledTaskService.create_task(db, data, current_user.id)
    except ValueError as exc:
        raise ApiError(400, "request.validation.invalid") from exc


@router.get("/scheduled-tasks/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await ScheduledTaskService.get_task(db, task_id)
    if not task:
        raise ApiError(404, "task.not_found")
    return task


@router.put("/scheduled-tasks/{task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    task_id: int,
    data: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await ScheduledTaskService.update_task(db, task_id, data, current_user.id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "任务不存在" else 400
        error_code = "task.not_found" if status_code == 404 else "request.validation.invalid"
        raise ApiError(status_code, error_code) from exc


@router.delete("/scheduled-tasks/{task_id}")
async def delete_scheduled_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await ScheduledTaskService.delete_task(db, task_id, current_user.id)
        return message_payload("task.deleted")
    except ValueError as exc:
        raise ApiError(404, "task.not_found") from exc


@router.post("/scheduled-tasks/{task_id}/run", response_model=ScheduledTaskRunResponse)
async def run_scheduled_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
):
    try:
        return await ScheduledTaskService.execute_task_by_id(task_id, trigger_source="manual")
    except ValueError as exc:
        raise ApiError(404, "task.not_found") from exc


@router.get("/scheduled-tasks/{task_id}/runs", response_model=List[ScheduledTaskRunResponse])
async def list_scheduled_task_runs(
    task_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await ScheduledTaskService.get_task(db, task_id)
    if not task:
        raise ApiError(404, "task.not_found")
    return await ScheduledTaskService.list_runs(db, task_id, limit=limit, offset=offset)


@router.get("/scheduled-task-runs/{run_id}", response_model=ScheduledTaskRunResponse)
async def get_scheduled_task_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await ScheduledTaskService.get_run(db, run_id)
    if not run:
        raise ApiError(404, "resource.not_found")
    return run
