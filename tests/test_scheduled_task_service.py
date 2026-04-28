import asyncio
from types import SimpleNamespace

import pytest

from backend.services import scheduled_task_service as service_module
from backend.services import scheduled_task_scheduler as scheduler_module
from backend.services.scheduled_task_service import ScheduledTaskService, normalize_schedule_config


class _FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added)


def _task(script_code, **kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", 1),
        script_code=script_code,
        timeout_seconds=kwargs.get("timeout_seconds", 1),
        max_concurrent_runs=kwargs.get("max_concurrent_runs", 1),
        last_run_at=None,
        last_status=None,
        last_error=None,
    )


@pytest.fixture(autouse=True)
def _clear_task_state(mocker):
    service_module._task_semaphores.clear()
    mocker.patch.object(ScheduledTaskService, "refresh_task_schedule", mocker.AsyncMock())
    yield
    service_module._task_semaphores.clear()


@pytest.mark.unit
def test_normalize_interval_schedule_from_every_unit():
    assert normalize_schedule_config("interval", {"every": 5, "unit": "minutes"}) == {"interval_seconds": 300}


@pytest.mark.unit
def test_normalize_cron_schedule_rejects_invalid_expression():
    with pytest.raises(ValueError):
        normalize_schedule_config("cron", {"expression": "not a cron"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_success_captures_print_and_result():
    db = _FakeDb()
    task = _task(
        """
async def run(context):
    print("hello", context.task.id)
    return {"ok": True, "task_id": context.task.id}
"""
    )

    run = await ScheduledTaskService._execute_task(db, task, "manual")

    assert run.status == "success"
    assert run.result == {"ok": True, "task_id": 1}
    assert "hello 1" in run.stdout
    assert task.last_status == "success"
    assert task.last_error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_records_script_exception():
    db = _FakeDb()
    task = _task(
        """
def run(context):
    print("before failure")
    raise RuntimeError("boom")
"""
    )

    run = await ScheduledTaskService._execute_task(db, task, "manual")

    assert run.status == "failed"
    assert run.error_message == "boom"
    assert "before failure" in run.stdout
    assert "RuntimeError: boom" in run.stderr
    assert task.last_status == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_records_timeout():
    db = _FakeDb()
    task = _task(
        """
import asyncio

async def run(context):
    await asyncio.sleep(0.05)
""",
        timeout_seconds=0.01,
    )

    run = await ScheduledTaskService._execute_task(db, task, "manual")

    assert run.status == "failed"
    assert "执行超时" in run.error_message
    assert task.last_status == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_skips_when_same_task_is_already_running():
    db = _FakeDb()
    task = _task(
        """
import asyncio

async def run(context):
    await asyncio.sleep(0.05)
    return {"done": True}
""",
        timeout_seconds=1,
    )

    first = asyncio.create_task(ScheduledTaskService._execute_task(db, task, "manual"))
    await asyncio.sleep(0.005)
    second = await ScheduledTaskService._execute_task(db, task, "scheduler")
    first_run = await first

    assert first_run.status == "success"
    assert second.status == "skipped"
    assert "仍在运行" in second.error_message


@pytest.mark.unit
def test_build_notification_payload_includes_execution_logs_on_failure():
    task = SimpleNamespace(id=7, name="失败任务")
    run = SimpleNamespace(
        id=33,
        status="failed",
        trigger_source="manual",
        started_at=None,
        finished_at=None,
        duration_ms=12,
        error_message="执行异常",
        result={"ok": False},
        stdout="stdout line",
        stderr="traceback line",
    )

    payload = ScheduledTaskService._build_notification_payload(task, run)

    assert payload["status"] == "failed"
    assert payload["alert_type"] == "定时任务执行"
    assert payload["datasource_name"] == "失败任务"
    assert payload["alert_id"] == 33
    assert payload["stdout"] == "stdout line"
    assert payload["stderr"] == "traceback line"
    assert "[error] 执行异常" in payload["execution_log"]
    assert "[stdout]\nstdout line" in payload["execution_log"]
    assert "[stderr]\ntraceback line" in payload["execution_log"]
    assert "[stderr]\ntraceback line" in payload["trigger_reason"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_task_schedule_adds_scheduler_job(mocker):
    task = _task("", id=9)
    task.enabled = True
    task.schedule_type = "interval"
    task.schedule_config = {"interval_seconds": 60}
    task.next_run_at = None

    class _Result:
        def scalar_one_or_none(self):
            return task

    class _Session:
        async def execute(self, statement):
            return _Result()

        async def commit(self):
            pass

    class _Context:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_scheduler = SimpleNamespace(
        get_job=mocker.Mock(return_value=None),
        add_job=mocker.Mock(return_value=SimpleNamespace(next_run_time=None)),
        remove_job=mocker.Mock(),
    )
    mocker.patch.object(scheduler_module, "_ensure_scheduler_started", return_value=fake_scheduler)
    mocker.patch.object(scheduler_module, "async_session", lambda: _Context())

    await scheduler_module.sync_task_schedule(9)

    fake_scheduler.add_job.assert_called_once()
    _, kwargs = fake_scheduler.add_job.call_args
    assert kwargs["id"] == "scheduled_task_9"
    assert kwargs["args"] == [9]
