"""Business logic and in-process Python execution for scheduled tasks."""
from __future__ import annotations

import asyncio
import inspect
import io
import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models.scheduled_task import ScheduledTask, ScheduledTaskRun
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.schemas.scheduled_task import ScheduledTaskCreate, ScheduledTaskUpdate
from backend.services.integration_service import IntegrationService
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

MAX_CAPTURED_LOG_CHARS = 200_000

_task_semaphores: Dict[int, Tuple[int, asyncio.Semaphore]] = {}


class ScheduledTaskContext:
    """Runtime context exposed to scheduled task scripts."""

    def __init__(self, db: AsyncSession, task: ScheduledTask, run: ScheduledTaskRun, logger_instance: logging.Logger):
        self.db = db
        self.task = task
        self.run = run
        self.logger = logger_instance

    def now(self):
        return now()

    async def log(self, level: str, message: str):
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func("[ScheduledTask:%s] %s", self.task.id, message)

    async def get_system_config(self, key: str) -> Optional[str]:
        from backend.models.system_config import SystemConfig
        from backend.utils.encryption import decrypt_value

        result = await self.db.execute(select(SystemConfig).where(SystemConfig.key == key, SystemConfig.is_active == True))
        config = result.scalar_one_or_none()
        if not config:
            return None
        if config.is_encrypted and config.value:
            return decrypt_value(config.value)
        return config.value

def _truncate_log(value: str) -> str:
    if len(value) <= MAX_CAPTURED_LOG_CHARS:
        return value
    return value[:MAX_CAPTURED_LOG_CHARS] + "\n... 日志过长，已截断 ..."


def _json_safe(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"value": None}
    if isinstance(value, dict):
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return {"value": repr(value)}
    try:
        json.dumps(value, ensure_ascii=False)
        return {"value": value}
    except TypeError:
        return {"value": repr(value)}


def _get_required_integration_params(integration) -> list[str]:
    schema = integration.config_schema or {}
    required = schema.get("required") or []
    return [key for key in required if isinstance(key, str) and key.strip()]


def _truncate_text(value: Any, max_chars: int = 1500) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... 内容过长，已截断 ..."


def _format_datetime(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.isoformat()


def _status_label(status: str | None) -> str:
    return {
        "success": "成功",
        "failed": "失败",
        "skipped": "跳过",
        "running": "运行中",
        "pending": "等待中",
    }.get(status or "", status or "-")


def _should_send_run_notification(policy: str | None, status: str | None) -> bool:
    if policy == "always":
        return status in {"success", "failed", "skipped"}
    if policy == "on_success":
        return status == "success"
    if policy == "on_failure":
        return status == "failed"
    return False


def normalize_schedule_config(schedule_type: str, schedule_config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize user-facing schedule config."""
    if schedule_type == "interval":
        if not isinstance(schedule_config, dict):
            raise ValueError("interval 调度配置必须是对象")

        interval_seconds = schedule_config.get("interval_seconds")
        if interval_seconds is None:
            every = schedule_config.get("every")
            unit = schedule_config.get("unit", "seconds")
            unit_seconds = {
                "seconds": 1,
                "minutes": 60,
                "hours": 3600,
                "days": 86400,
            }
            if unit not in unit_seconds:
                raise ValueError("interval.unit 只能是 seconds/minutes/hours/days")
            try:
                interval_seconds = int(every) * unit_seconds[unit]
            except (TypeError, ValueError):
                raise ValueError("interval.every 必须是正整数")

        try:
            interval_seconds = int(interval_seconds)
        except (TypeError, ValueError):
            raise ValueError("interval_seconds 必须是正整数")
        if interval_seconds < 1:
            raise ValueError("interval_seconds 必须大于 0")
        return {"interval_seconds": interval_seconds}

    if schedule_type == "cron":
        if not isinstance(schedule_config, dict):
            raise ValueError("cron 调度配置必须是对象")
        expression = str(schedule_config.get("expression") or "").strip()
        if not expression:
            raise ValueError("cron.expression 不能为空")
        CronTrigger.from_crontab(expression)
        return {"expression": expression}

    raise ValueError("schedule_type 只能是 interval 或 cron")


def build_trigger(schedule_type: str, schedule_config: Dict[str, Any]):
    normalized = normalize_schedule_config(schedule_type, schedule_config)
    if schedule_type == "interval":
        return IntervalTrigger(seconds=normalized["interval_seconds"])
    return CronTrigger.from_crontab(normalized["expression"])


def get_task_job_id(task_id: int) -> str:
    return f"scheduled_task_{task_id}"


def _get_task_semaphore(task: ScheduledTask) -> asyncio.Semaphore:
    limit = max(1, int(task.max_concurrent_runs or 1))
    existing = _task_semaphores.get(task.id)
    if existing and existing[0] == limit:
        return existing[1]
    semaphore = asyncio.Semaphore(limit)
    _task_semaphores[task.id] = (limit, semaphore)
    return semaphore


class ScheduledTaskService:
    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        keyword: Optional[str] = None,
        enabled: Optional[bool] = None,
        last_status: Optional[str] = None,
    ) -> List[ScheduledTask]:
        query = alive_select(ScheduledTask)
        conditions = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(or_(ScheduledTask.name.ilike(pattern), ScheduledTask.description.ilike(pattern)))
        if enabled is not None:
            conditions.append(ScheduledTask.enabled == enabled)
        if last_status:
            conditions.append(ScheduledTask.last_status == last_status)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(ScheduledTask.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_task(db: AsyncSession, task_id: int) -> Optional[ScheduledTask]:
        return await get_alive_by_id(db, ScheduledTask, task_id)

    @staticmethod
    async def create_task(db: AsyncSession, data: ScheduledTaskCreate, user_id: Optional[int]) -> ScheduledTask:
        normalized_config = normalize_schedule_config(data.schedule_type, data.schedule_config)
        task = ScheduledTask(
            name=data.name,
            description=data.description,
            script_code=data.script_code,
            schedule_type=data.schedule_type,
            schedule_config=normalized_config,
            enabled=data.enabled,
            timeout_seconds=data.timeout_seconds,
            max_concurrent_runs=data.max_concurrent_runs,
            notification_policy=data.notification_policy,
            notification_targets=ScheduledTaskService._serialize_notification_targets(data.notification_targets),
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        await ScheduledTaskService.refresh_task_schedule(task.id)
        return task

    @staticmethod
    async def update_task(db: AsyncSession, task_id: int, data: ScheduledTaskUpdate, user_id: Optional[int]) -> ScheduledTask:
        task = await get_alive_by_id(db, ScheduledTask, task_id)
        if not task:
            raise ValueError("任务不存在")

        next_schedule_type = data.schedule_type if data.schedule_type is not None else task.schedule_type
        next_schedule_config = data.schedule_config if data.schedule_config is not None else task.schedule_config
        normalized_config = normalize_schedule_config(next_schedule_type, next_schedule_config)

        if data.name is not None:
            task.name = data.name
        if "description" in data.model_fields_set:
            task.description = data.description
        if data.script_code is not None:
            task.script_code = data.script_code
        if data.schedule_type is not None:
            task.schedule_type = data.schedule_type
        if data.schedule_config is not None or data.schedule_type is not None:
            task.schedule_config = normalized_config
        if data.enabled is not None:
            task.enabled = data.enabled
        if data.timeout_seconds is not None:
            task.timeout_seconds = data.timeout_seconds
        if data.max_concurrent_runs is not None:
            task.max_concurrent_runs = data.max_concurrent_runs
            _task_semaphores.pop(task.id, None)
        if data.notification_policy is not None:
            task.notification_policy = data.notification_policy
        if data.notification_targets is not None:
            task.notification_targets = ScheduledTaskService._serialize_notification_targets(data.notification_targets)

        task.updated_by_id = user_id
        task.updated_at = now()
        await db.commit()
        await db.refresh(task)
        await ScheduledTaskService.refresh_task_schedule(task.id)
        return task

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: int, user_id: Optional[int]) -> None:
        task = await get_alive_by_id(db, ScheduledTask, task_id)
        if not task:
            raise ValueError("任务不存在")
        task.soft_delete(user_id)
        task.enabled = False
        task.updated_by_id = user_id
        task.updated_at = now()
        await db.commit()
        _task_semaphores.pop(task_id, None)
        await ScheduledTaskService.refresh_task_schedule(task_id)

    @staticmethod
    async def list_runs(db: AsyncSession, task_id: int, limit: int = 50, offset: int = 0) -> List[ScheduledTaskRun]:
        result = await db.execute(
            select(ScheduledTaskRun)
            .where(ScheduledTaskRun.task_id == task_id)
            .order_by(desc(ScheduledTaskRun.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_run(db: AsyncSession, run_id: int) -> Optional[ScheduledTaskRun]:
        result = await db.execute(select(ScheduledTaskRun).where(ScheduledTaskRun.id == run_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def refresh_task_schedule(task_id: int) -> None:
        from backend.services.scheduled_task_scheduler import sync_task_schedule

        await sync_task_schedule(task_id)

    @staticmethod
    async def execute_task_by_id(task_id: int, trigger_source: str = "manual") -> ScheduledTaskRun:
        async with async_session() as db:
            task = await get_alive_by_id(db, ScheduledTask, task_id)
            if not task:
                raise ValueError("任务不存在")
            return await ScheduledTaskService._execute_task(db, task, trigger_source)

    @staticmethod
    async def _execute_task(db: AsyncSession, task: ScheduledTask, trigger_source: str) -> ScheduledTaskRun:
        run = ScheduledTaskRun(
            task_id=task.id,
            trigger_source=trigger_source,
            status="pending",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        semaphore = _get_task_semaphore(task)
        acquired = False
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.001)
            acquired = True
        except asyncio.TimeoutError:
            finished = now()
            run.status = "skipped"
            run.started_at = finished
            run.finished_at = finished
            run.duration_ms = 0
            run.error_message = "任务仍在运行，已跳过本次触发"
            run.stderr = run.error_message
            task.last_run_at = finished
            task.last_status = "skipped"
            task.last_error = run.error_message
            await db.commit()
            await db.refresh(run)
            await ScheduledTaskService._notify_run_completed(db, task, run)
            return run

        started = now()
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        run.status = "running"
        run.started_at = started
        await db.commit()
        await db.refresh(run)

        try:
            result = await asyncio.wait_for(
                ScheduledTaskService._run_script(db, task, run, stdout_buffer),
                timeout=task.timeout_seconds,
            )
            finished = now()
            run.status = "success"
            run.result = _json_safe(result)
            run.stdout = _truncate_log(stdout_buffer.getvalue())
            run.stderr = _truncate_log(stderr_buffer.getvalue())
            run.finished_at = finished
            run.duration_ms = int((finished - started).total_seconds() * 1000)
            task.last_run_at = finished
            task.last_status = "success"
            task.last_error = None
        except asyncio.TimeoutError:
            finished = now()
            message = f"执行超时（超过 {task.timeout_seconds} 秒）"
            stderr_buffer.write(message)
            run.status = "failed"
            run.stdout = _truncate_log(stdout_buffer.getvalue())
            run.stderr = _truncate_log(stderr_buffer.getvalue())
            run.error_message = message
            run.finished_at = finished
            run.duration_ms = int((finished - started).total_seconds() * 1000)
            task.last_run_at = finished
            task.last_status = "failed"
            task.last_error = message
        except Exception as exc:
            finished = now()
            tb = traceback.format_exc()
            stderr_buffer.write(tb)
            run.status = "failed"
            run.stdout = _truncate_log(stdout_buffer.getvalue())
            run.stderr = _truncate_log(stderr_buffer.getvalue())
            run.error_message = str(exc)
            run.finished_at = finished
            run.duration_ms = int((finished - started).total_seconds() * 1000)
            task.last_run_at = finished
            task.last_status = "failed"
            task.last_error = str(exc)
            logger.error("定时任务执行失败 task_id=%s run_id=%s: %s", task.id, run.id, exc, exc_info=True)
        finally:
            if acquired:
                semaphore.release()

        await db.commit()
        await db.refresh(run)
        await ScheduledTaskService.refresh_task_schedule(task.id)
        await ScheduledTaskService._notify_run_completed(db, task, run)
        return run

    @staticmethod
    def _serialize_notification_targets(targets: Optional[List[Any]]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for index, target in enumerate(targets or []):
            data = target.model_dump() if hasattr(target, "model_dump") else dict(target)
            integration_id = data.get("integration_id")
            if not integration_id:
                continue
            name = str(data.get("name") or f"通知目标 #{index + 1}").strip()
            target_id = str(data.get("target_id") or f"target_{index + 1}").strip()
            serialized.append({
                "target_id": target_id,
                "integration_id": int(integration_id),
                "name": name,
                "enabled": data.get("enabled", True) is not False,
                "params": IntegrationService.encrypt_sensitive_params(data.get("params") or {}),
            })
        return serialized

    @staticmethod
    def _build_notification_payload(task: ScheduledTask, run: ScheduledTaskRun) -> Dict[str, Any]:
        status_text = _status_label(run.status)
        severity = "info" if run.status == "success" else "warning"
        title = f"定时任务执行{status_text}：{task.name}"
        truncated_stdout = _truncate_text(run.stdout, 1200) if run.stdout else ""
        truncated_stderr = _truncate_text(run.stderr, 1200) if run.stderr else ""

        lines = [
            f"任务：{task.name}",
            f"状态：{status_text}",
            f"触发来源：{'调度器' if run.trigger_source == 'scheduler' else '手动执行'}",
            f"开始时间：{_format_datetime(run.started_at)}",
            f"结束时间：{_format_datetime(run.finished_at)}",
            f"耗时：{run.duration_ms if run.duration_ms is not None else '-'} ms",
        ]
        if run.error_message:
            lines.append(f"错误：{_truncate_text(run.error_message, 800)}")
        if run.result:
            lines.append("返回结果：")
            lines.append(_truncate_text(json.dumps(run.result, ensure_ascii=False, indent=2), 1200))
        if run.stdout:
            lines.append("stdout：")
            lines.append(truncated_stdout)
        if run.stderr:
            lines.append("stderr：")
            lines.append(truncated_stderr)

        execution_log = ""
        if run.status == "failed":
            log_parts = []
            if run.error_message:
                log_parts.append(f"[error] {_truncate_text(run.error_message, 800)}")
            if truncated_stdout:
                log_parts.append(f"[stdout]\n{truncated_stdout}")
            if truncated_stderr:
                log_parts.append(f"[stderr]\n{truncated_stderr}")
            execution_log = "\n\n".join(log_parts)
        trigger_reason = execution_log if execution_log else (run.error_message or "")

        return {
            "title": title,
            "content": "\n".join(lines),
            "severity": severity,
            "source": "scheduled_task",
            "alert_type": "定时任务执行",
            "datasource_name": task.name,
            "alert_id": run.id,
            "task_id": task.id,
            "task_name": task.name,
            "run_id": run.id,
            "status": run.status,
            "status_text": status_text,
            "trigger_source": run.trigger_source,
            "started_at": _format_datetime(run.started_at),
            "finished_at": _format_datetime(run.finished_at),
            "duration_ms": run.duration_ms,
            "error_message": run.error_message,
            "result": run.result,
            "stdout": truncated_stdout,
            "stderr": truncated_stderr,
            "execution_log": execution_log,
            "trigger_reason": trigger_reason,
            "timestamp": _format_datetime(run.finished_at or now()),
        }

    @staticmethod
    async def _notify_run_completed(db: AsyncSession, task: ScheduledTask, run: ScheduledTaskRun) -> None:
        policy = getattr(task, "notification_policy", "never") or "never"
        targets = getattr(task, "notification_targets", None) or []
        if not targets or not _should_send_run_notification(policy, run.status):
            return

        from backend.models.integration import Integration, IntegrationExecutionLog
        from backend.services.integration_executor import IntegrationExecutor

        payload = ScheduledTaskService._build_notification_payload(task, run)

        for target in targets:
            if not isinstance(target, dict) or not target.get("enabled", True):
                continue
            integration_id = target.get("integration_id")
            if not integration_id:
                continue

            try:
                integration = await get_alive_by_id(db, Integration, int(integration_id))
                if not integration or not integration.is_enabled or integration.integration_type != "outbound_notification":
                    logger.warning("定时任务通知目标不可用 task_id=%s run_id=%s integration_id=%s", task.id, run.id, integration_id)
                    continue

                params = target.get("params") or {}
                target_id = target.get("target_id")
                target_name = target.get("name") or integration.name
                start_time = now()
                required_params = _get_required_integration_params(integration)
                missing_params = [key for key in required_params if not params.get(key)]

                if missing_params:
                    error_message = f"Integration 缺少必填参数: {', '.join(missing_params)}"
                    db.add(IntegrationExecutionLog(
                        integration_id=integration.id,
                        target_type="scheduled_task_notification",
                        target_ref=str(target_id) if target_id is not None else None,
                        target_name=target_name,
                        params_snapshot=params,
                        payload_summary={"task_id": task.id, "run_id": run.id, "status": run.status},
                        trigger_source="scheduled_task",
                        trigger_ref_id=str(run.id),
                        status="failed",
                        execution_time_ms=0,
                        result={"success": False, "message": error_message, "data": {"missing_params": missing_params}},
                        error_message=error_message,
                    ))
                    await db.commit()
                    continue

                result = await IntegrationExecutor(db, logger).execute_notification(integration.code, params, payload)
                execution_time_ms = int((now() - start_time).total_seconds() * 1000)
                success = bool(result.get("success"))
                db.add(IntegrationExecutionLog(
                    integration_id=integration.id,
                    target_type="scheduled_task_notification",
                    target_ref=str(target_id) if target_id is not None else None,
                    target_name=target_name,
                    params_snapshot=params,
                    payload_summary={"task_id": task.id, "run_id": run.id, "status": run.status},
                    trigger_source="scheduled_task",
                    trigger_ref_id=str(run.id),
                    status="success" if success else "failed",
                    execution_time_ms=execution_time_ms,
                    result=result,
                    error_message=result.get("message") if not success else None,
                ))
                await db.commit()
            except Exception as exc:
                logger.error("定时任务结果通知发送失败 task_id=%s run_id=%s: %s", task.id, run.id, exc, exc_info=True)
                try:
                    db.add(IntegrationExecutionLog(
                        integration_id=int(integration_id),
                        target_type="scheduled_task_notification",
                        target_ref=str(target.get("target_id")) if target.get("target_id") is not None else None,
                        target_name=target.get("name"),
                        params_snapshot=target.get("params") or {},
                        payload_summary={"task_id": task.id, "run_id": run.id, "status": run.status},
                        trigger_source="scheduled_task",
                        trigger_ref_id=str(run.id),
                        status="failed",
                        execution_time_ms=0,
                        error_message=str(exc),
                    ))
                    await db.commit()
                except Exception:
                    logger.error("写入定时任务通知失败日志失败 task_id=%s run_id=%s", task.id, run.id, exc_info=True)

    @staticmethod
    async def _run_script(
        db: AsyncSession,
        task: ScheduledTask,
        run: ScheduledTaskRun,
        stdout_buffer: io.StringIO,
    ) -> Any:
        context = ScheduledTaskContext(db, task, run, logger)

        def captured_print(*values, sep=" ", end="\n", file=None, flush=False):
            text = sep.join(str(value) for value in values) + end
            stdout_buffer.write(text)

        builtins_dict = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
        safe_builtins = dict(builtins_dict)
        safe_builtins["print"] = captured_print
        namespace = {
            "__builtins__": safe_builtins,
            "context": context,
        }
        exec(task.script_code, namespace, namespace)
        runner = namespace.get("run")
        if runner is None:
            raise ValueError("脚本中未定义 run(context) 函数")
        if not callable(runner):
            raise ValueError("run 必须是可调用函数")

        signature = inspect.signature(runner)
        positional_params = [
            param for param in signature.parameters.values()
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional_params) != 1:
            raise ValueError("run 函数必须且只能接收一个参数：context")
        if positional_params[0].kind == inspect.Parameter.POSITIONAL_ONLY or positional_params[0].name != "context":
            raise ValueError("run 函数签名必须为 run(context)")

        result = runner(context)
        if inspect.isawaitable(result):
            result = await result
        return result

    @staticmethod
    async def count_runs(db: AsyncSession, task_id: int) -> int:
        result = await db.execute(select(func.count()).select_from(ScheduledTaskRun).where(ScheduledTaskRun.task_id == task_id))
        return int(result.scalar() or 0)
