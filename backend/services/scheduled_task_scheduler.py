"""APScheduler integration for user-managed scheduled tasks."""
from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from backend.database import async_session
from backend.models.scheduled_task import ScheduledTask
from backend.models.soft_delete import alive_filter
from backend.services.scheduled_task_service import ScheduledTaskService, build_trigger, get_task_job_id

logger = logging.getLogger(__name__)

scheduler: Optional[AsyncIOScheduler] = None


def _ensure_scheduler_started() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
        scheduler.start()
        logger.info("任务调度器已启动")
    return scheduler


async def execute_scheduled_task(task_id: int):
    """Entry point called by APScheduler."""
    try:
        await ScheduledTaskService.execute_task_by_id(task_id, trigger_source="scheduler")
    except Exception as exc:
        logger.error("调度任务执行入口失败 task_id=%s: %s", task_id, exc, exc_info=True)


async def sync_task_schedule(task_id: int) -> None:
    """Create, update, or remove the APScheduler job for one task."""
    active_scheduler = _ensure_scheduler_started()
    job_id = get_task_job_id(task_id)

    async with async_session() as db:
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, alive_filter(ScheduledTask))
        )
        task = result.scalar_one_or_none()

        if not task or not task.enabled:
            if active_scheduler.get_job(job_id):
                active_scheduler.remove_job(job_id)
            if task:
                task.next_run_at = None
                await db.commit()
            return

        try:
            trigger = build_trigger(task.schedule_type, task.schedule_config)
            job = active_scheduler.add_job(
                execute_scheduled_task,
                trigger=trigger,
                args=[task.id],
                id=job_id,
                replace_existing=True,
                coalesce=True,
                max_instances=max(1, int(task.max_concurrent_runs or 1)),
            )
            task.next_run_at = job.next_run_time
            await db.commit()
            logger.info("已刷新任务调度 task_id=%s next_run_at=%s", task.id, task.next_run_at)
        except Exception as exc:
            task.next_run_at = None
            task.last_error = f"调度配置无效: {exc}"
            await db.commit()
            logger.error("刷新任务调度失败 task_id=%s: %s", task.id, exc, exc_info=True)


async def refresh_all_scheduled_tasks() -> None:
    active_scheduler = _ensure_scheduler_started()
    existing_job_ids = {job.id for job in active_scheduler.get_jobs() if job.id.startswith("scheduled_task_")}

    async with async_session() as db:
        result = await db.execute(
            select(ScheduledTask.id).where(ScheduledTask.enabled == True, alive_filter(ScheduledTask))
        )
        enabled_task_ids = {int(task_id) for task_id in result.scalars().all()}

    for stale_job_id in existing_job_ids - {get_task_job_id(task_id) for task_id in enabled_task_ids}:
        active_scheduler.remove_job(stale_job_id)

    for task_id in enabled_task_ids:
        await sync_task_schedule(task_id)


async def start_scheduled_task_scheduler() -> None:
    logger.info("正在启动任务调度器...")
    await refresh_all_scheduled_tasks()
    logger.info("任务调度器启动完成")


def stop_scheduled_task_scheduler() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("任务调度器已停止")
