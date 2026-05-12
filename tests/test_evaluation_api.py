from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.routers import evaluation


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return _ScalarsResult(self._rows)


def _client(db, user=None):
    app = FastAPI()
    app.include_router(evaluation.router)
    app.dependency_overrides[get_current_user] = lambda: user or SimpleNamespace(id=2, is_admin=False)

    async def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override
    return TestClient(app)


def _suite():
    return SimpleNamespace(
        id=1,
        name="MySQL 标准套件",
        description="desc",
        case_ids=["mysql_slow_query_missing_index"],
        is_builtin="yes",
    )


def _run():
    return SimpleNamespace(
        id=10,
        suite_id=1,
        suite_name="MySQL 标准套件",
        ai_model_id=1,
        ai_model_name="qwen",
        judge_model_id=1,
        status="completed",
        total_cases=1,
        completed_cases=1,
        failed_cases=0,
        total_score=88.5,
        dimension_summary={"root_cause": 28},
        error_message=None,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _case_result(session_id=99):
    return SimpleNamespace(
        id=20,
        run_id=10,
        case_id="mysql_slow_query_missing_index",
        case_title="Missing index",
        case_category="slow_query",
        status="completed",
        score=90,
        dimension_scores=[],
        judge_feedback={},
        tool_call_summary={},
        conclusion_md="结论",
        latency_ms=1200,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        session_id=session_id,
        error_message=None,
        finished_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )


def _message(role, content, message_id=1):
    return SimpleNamespace(
        id=message_id,
        role=role,
        content=content,
        run_id=None,
        render_segments=None,
        status=None,
        tool_calls=None,
        attachments=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _hidden_session(session_id=99):
    deleted = {"called": False, "user_id": None}

    def _soft_delete(user_id):
        deleted["called"] = True
        deleted["user_id"] = user_id

    return SimpleNamespace(
        id=session_id,
        is_hidden=True,
        soft_delete=_soft_delete,
        _deleted=deleted,
    )


@pytest.mark.api
def test_normal_user_can_access_eval_cases_and_runs(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result(rows=[_suite()]),
        _Result(rows=[_run()]),
    ])
    mocker.patch("backend.routers.evaluation.ensure_builtin_suite", AsyncMock(return_value=_suite()))

    client = _client(db)

    cases_response = client.get("/api/eval/cases")
    assert cases_response.status_code == 200
    assert cases_response.json()

    suites_response = client.get("/api/eval/suites")
    assert suites_response.status_code == 200
    assert suites_response.json()[0]["name"] == "MySQL 标准套件"

    runs_response = client.get("/api/eval/runs")
    assert runs_response.status_code == 200
    assert runs_response.json()[0]["id"] == 10


@pytest.mark.api
def test_eval_replay_reads_messages_through_result_session_only():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result(one=_case_result(session_id=99)),
        _Result(one=SimpleNamespace(
            id=99,
            title="[eval] mysql_slow_query_missing_index",
            ai_model_id=1,
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
        )),
        _Result(rows=[
            _message("user", "为什么慢", 1),
            _message("assistant", "缺索引", 2),
        ]),
    ])

    response = _client(db).get("/api/eval/runs/10/results/mysql_slow_query_missing_index/replay")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == 99
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant"]


@pytest.mark.api
def test_eval_replay_returns_404_without_eval_result():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(one=None))

    response = _client(db).get("/api/eval/runs/10/results/missing/replay")

    assert response.status_code == 404


@pytest.mark.api
def test_eval_replay_returns_404_without_session():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(one=_case_result(session_id=None)))

    response = _client(db).get("/api/eval/runs/10/results/mysql_slow_query_missing_index/replay")

    assert response.status_code == 404


@pytest.mark.api
def test_create_eval_run_rejects_inactive_ai_model(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result(one=_suite()),
        _Result(one=None),
    ])
    mocker.patch("backend.routers.evaluation.asyncio.create_task")

    response = _client(db).post("/api/eval/runs", json={"suite_id": 1, "ai_model_id": 99})

    assert response.status_code == 404
    assert "ai_model" in response.text


@pytest.mark.api
def test_create_eval_run_rejects_inactive_judge_model(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result(one=_suite()),
        _Result(one=SimpleNamespace(id=1, name="diagnosis", is_active=True)),
        _Result(one=None),
    ])
    mocker.patch("backend.routers.evaluation.asyncio.create_task")

    response = _client(db).post(
        "/api/eval/runs",
        json={"suite_id": 1, "ai_model_id": 1, "judge_model_id": 2},
    )

    assert response.status_code == 404
    assert "judge_model" in response.text


@pytest.mark.api
def test_delete_eval_run_cleans_up_hidden_replay_and_results():
    db = AsyncMock()
    run = SimpleNamespace(id=10, status="completed")
    result_row = _case_result(session_id=99)
    hidden_session = _hidden_session(99)
    hidden_message = _message("assistant", "缺索引", 2)

    deleted_message = {"called": False, "user_id": None}

    def _msg_soft_delete(user_id):
        deleted_message["called"] = True
        deleted_message["user_id"] = user_id

    hidden_message.soft_delete = _msg_soft_delete

    db.execute = AsyncMock(side_effect=[
        _Result(one=run),
        _Result(rows=[result_row]),
        _Result(rows=[hidden_session]),
        _Result(rows=[hidden_message]),
        _Result(),
        _Result(),
    ])

    response = _client(db).delete("/api/eval/runs/10")

    assert response.status_code == 200
    assert response.json()["run_id"] == 10
    assert hidden_session._deleted == {"called": True, "user_id": 2}
    assert deleted_message == {"called": True, "user_id": 2}
    assert db.execute.await_count == 6
    delete_results_stmt = db.execute.await_args_list[4].args[0]
    delete_run_stmt = db.execute.await_args_list[5].args[0]
    assert "DELETE FROM eval_case_result" in str(delete_results_stmt)
    assert "DELETE FROM eval_run" in str(delete_run_stmt)
    db.commit.assert_awaited_once()


@pytest.mark.api
def test_delete_eval_run_allows_active_run():
    db = AsyncMock()
    evaluation._RUN_TASKS.pop(10, None)
    db.execute = AsyncMock(side_effect=[
        _Result(one=SimpleNamespace(id=10, status="running")),
        _Result(rows=[]),
        _Result(),
        _Result(),
    ])

    response = _client(db).delete("/api/eval/runs/10")

    assert response.status_code == 200
    assert response.json()["run_id"] == 10
    assert db.execute.await_count == 4
    db.commit.assert_awaited_once()


@pytest.mark.api
def test_delete_eval_run_compat_endpoint():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result(one=SimpleNamespace(id=10, status="completed")),
        _Result(rows=[]),
        _Result(),
        _Result(),
    ])

    response = _client(db).post("/api/eval/runs/10/delete", json={})

    assert response.status_code == 200
    assert response.json()["run_id"] == 10


@pytest.mark.api
def test_delete_eval_run_returns_404_when_missing():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(one=None))

    response = _client(db).delete("/api/eval/runs/999")

    assert response.status_code == 404
