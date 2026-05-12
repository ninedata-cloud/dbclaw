"""AI diagnostic evaluation API."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session, get_db
from backend.dependencies import get_current_user
from backend.evaluation.builtin_suite import ensure_builtin_suite
from backend.evaluation.case_loader import EvalCase, get_case, load_all_cases
from backend.evaluation.runner import execute_run
from backend.models.ai_model import AIModel
from backend.models.diagnostic_session import ChatMessage, DiagnosticSession
from backend.models.evaluation import EvalCaseResult, EvalRun, EvalSuite
from backend.models.soft_delete import alive_select
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eval", tags=["evaluation"])
_RUN_TASKS: Dict[int, asyncio.Task[Any]] = {}


# ---------------------------------------------------------------- DTOs

class CaseSummary(BaseModel):
    id: str
    title: str
    category: str
    db_type: str
    difficulty: str
    description: Optional[str] = None
    required_tools: List[str]
    forbidden_tools: List[str]
    min_tool_rounds: int
    max_tool_rounds: int


class CaseDetail(CaseSummary):
    user_message: str
    fixtures: List[Dict[str, Any]]
    root_causes: List[str]
    required_actions: List[Dict[str, Any]]
    conclusion_must_contain: List[str]
    conclusion_must_not_contain: List[str]


class SuiteDTO(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    case_ids: List[str]
    is_builtin: bool


class RunCreateRequest(BaseModel):
    suite_id: Optional[int] = None
    case_ids: Optional[List[str]] = None
    ai_model_id: Optional[int] = None
    judge_model_id: Optional[int] = None


class RunDTO(BaseModel):
    id: int
    suite_id: Optional[int]
    suite_name: Optional[str]
    ai_model_id: Optional[int]
    ai_model_name: Optional[str]
    judge_model_id: Optional[int]
    status: str
    total_cases: int
    completed_cases: int
    failed_cases: int
    total_score: Optional[float]
    dimension_summary: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime


class CaseResultSummary(BaseModel):
    id: int
    run_id: int
    case_id: str
    case_title: Optional[str]
    case_category: Optional[str]
    status: str
    score: Optional[float]
    latency_ms: Optional[int]
    total_tokens: Optional[int]
    session_id: Optional[int]
    error_message: Optional[str]
    finished_at: Optional[datetime]


class CaseResultDetail(CaseResultSummary):
    dimension_scores: Optional[List[Dict[str, Any]]]
    judge_feedback: Optional[Dict[str, Any]]
    tool_call_summary: Optional[Dict[str, Any]]
    conclusion_md: Optional[str]


class EvalReplayMessageDTO(BaseModel):
    id: int
    role: str
    content: str
    run_id: Optional[str] = None
    render_segments: Optional[Any] = None
    status: Optional[str] = None
    tool_calls: Optional[Any] = None
    attachments: Optional[List[Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    created_at: Optional[datetime] = None


class EvalReplayDTO(BaseModel):
    run_id: int
    case_id: str
    case_title: Optional[str]
    case_category: Optional[str]
    session_id: int
    session_title: Optional[str]
    ai_model_id: Optional[int]
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    messages: List[EvalReplayMessageDTO]


# ---------------------------------------------------------------- helpers

def _case_summary(case: EvalCase) -> CaseSummary:
    return CaseSummary(
        id=case.id,
        title=case.title,
        category=case.category,
        db_type=case.db_type,
        difficulty=case.difficulty,
        description=case.description,
        required_tools=case.expected.required_tools,
        forbidden_tools=case.expected.forbidden_tools,
        min_tool_rounds=case.expected.min_tool_rounds,
        max_tool_rounds=case.expected.max_tool_rounds,
    )


def _case_detail(case: EvalCase) -> CaseDetail:
    return CaseDetail(
        **_case_summary(case).model_dump(),
        user_message=case.user_message,
        fixtures=[
            {"tool": f.tool, "args": f.args, "response": f.response}
            for f in case.fixtures
        ],
        root_causes=case.expected.root_causes,
        required_actions=case.expected.required_actions,
        conclusion_must_contain=case.expected.conclusion_must_contain,
        conclusion_must_not_contain=case.expected.conclusion_must_not_contain,
    )


def _suite_dto(suite: EvalSuite) -> SuiteDTO:
    return SuiteDTO(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        case_ids=list(suite.case_ids or []),
        is_builtin=(suite.is_builtin == "yes"),
    )


def _run_dto(run: EvalRun) -> RunDTO:
    return RunDTO(
        id=run.id,
        suite_id=run.suite_id,
        suite_name=run.suite_name,
        ai_model_id=run.ai_model_id,
        ai_model_name=run.ai_model_name,
        judge_model_id=run.judge_model_id,
        status=run.status,
        total_cases=run.total_cases or 0,
        completed_cases=run.completed_cases or 0,
        failed_cases=run.failed_cases or 0,
        total_score=float(run.total_score) if run.total_score is not None else None,
        dimension_summary=run.dimension_summary,
        error_message=run.error_message,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


def _result_summary(row: EvalCaseResult) -> CaseResultSummary:
    return CaseResultSummary(
        id=row.id,
        run_id=row.run_id,
        case_id=row.case_id,
        case_title=row.case_title,
        case_category=row.case_category,
        status=row.status,
        score=float(row.score) if row.score is not None else None,
        latency_ms=row.latency_ms,
        total_tokens=row.total_tokens,
        session_id=row.session_id,
        error_message=row.error_message,
        finished_at=row.finished_at,
    )


def _result_detail(row: EvalCaseResult) -> CaseResultDetail:
    return CaseResultDetail(
        **_result_summary(row).model_dump(),
        dimension_scores=row.dimension_scores,
        judge_feedback=row.judge_feedback,
        tool_call_summary=row.tool_call_summary,
        conclusion_md=row.conclusion_md,
    )


def _replay_message(row: ChatMessage) -> EvalReplayMessageDTO:
    return EvalReplayMessageDTO(
        id=row.id,
        role=row.role,
        content=row.content,
        run_id=row.run_id,
        render_segments=row.render_segments,
        status=row.status,
        tool_calls=row.tool_calls,
        attachments=row.attachments,
        input_tokens=row.input_tokens or 0,
        output_tokens=row.output_tokens or 0,
        total_tokens=row.total_tokens or 0,
        created_at=row.created_at,
    )


async def _resolve_active_model(db: AsyncSession, model_id: Optional[int], label: str) -> Optional[AIModel]:
    if model_id is None:
        return None

    result = await db.execute(
        select(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail=f"{label} not found or inactive")
    return model


async def _cancel_run_task(run_id: int) -> None:
    task = _RUN_TASKS.pop(run_id, None)
    if not task or task.done():
        return

    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=5)
    except asyncio.CancelledError:
        pass
    except asyncio.TimeoutError:
        logger.warning("Timed out waiting for eval run %s task cancellation", run_id)


# ---------------------------------------------------------------- cases

@router.get("/cases", response_model=List[CaseSummary])
async def list_cases(
    db_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    cases = list(load_all_cases().values())
    if db_type:
        cases = [c for c in cases if c.db_type == db_type]
    if category:
        cases = [c for c in cases if c.category == category]
    cases.sort(key=lambda c: (c.db_type, c.category, c.id))
    return [_case_summary(c) for c in cases]


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def get_case_detail(case_id: str, user: User = Depends(get_current_user)):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return _case_detail(case)


# ---------------------------------------------------------------- suites

@router.get("/suites", response_model=List[SuiteDTO])
async def list_suites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_builtin_suite(db)
    result = await db.execute(select(EvalSuite).order_by(EvalSuite.id))
    return [_suite_dto(s) for s in result.scalars().all()]


@router.get("/suites/{suite_id}", response_model=SuiteDTO)
async def get_suite(
    suite_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(EvalSuite).filter(EvalSuite.id == suite_id))
    suite = result.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="suite not found")
    return _suite_dto(suite)


# ---------------------------------------------------------------- runs

@router.post("/runs", response_model=RunDTO)
async def create_run(
    payload: RunCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    suite: Optional[EvalSuite] = None
    case_ids: List[str]

    if payload.suite_id is not None:
        result = await db.execute(select(EvalSuite).filter(EvalSuite.id == payload.suite_id))
        suite = result.scalar_one_or_none()
        if not suite:
            raise HTTPException(status_code=404, detail="suite not found")
        case_ids = list(suite.case_ids or [])
    elif payload.case_ids:
        case_ids = list(payload.case_ids)
    else:
        await ensure_builtin_suite(db)
        result = await db.execute(
            select(EvalSuite).filter(EvalSuite.is_builtin == "yes").order_by(EvalSuite.id)
        )
        suite = result.scalars().first()
        case_ids = list(suite.case_ids or []) if suite else []

    if not case_ids:
        raise HTTPException(status_code=400, detail="no cases to run")

    # validate every case_id resolves
    all_cases = load_all_cases()
    missing = [cid for cid in case_ids if cid not in all_cases]
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown cases: {missing}")

    judge_model_id = payload.judge_model_id or payload.ai_model_id
    ai_model = await _resolve_active_model(db, payload.ai_model_id, "ai_model")
    await _resolve_active_model(db, judge_model_id, "judge_model")

    run = EvalRun(
        suite_id=suite.id if suite else None,
        suite_name=suite.name if suite else "ad-hoc",
        ai_model_id=payload.ai_model_id,
        ai_model_name=ai_model.name if ai_model else None,
        judge_model_id=judge_model_id,
        user_id=user.id,
        status="pending",
        total_cases=len(case_ids),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Spawn background task with its own DB session
    run_id = run.id
    user_id = user.id

    async def _spawn():
        async with async_session() as bg_db:
            try:
                await execute_run(
                    run_id=run_id,
                    db=bg_db,
                    case_ids=case_ids,
                    ai_model_id=payload.ai_model_id,
                    judge_model_id=judge_model_id,
                    user_id=user_id,
                    concurrency=1,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("eval run %s crashed", run_id)
                # mark run as failed
                async with async_session() as fail_db:
                    res = await fail_db.execute(select(EvalRun).filter(EvalRun.id == run_id))
                    failed_run = res.scalar_one_or_none()
                    if failed_run:
                        failed_run.status = "failed"
                        failed_run.error_message = f"{type(exc).__name__}: {exc}"
                        failed_run.finished_at = datetime.now(timezone.utc)
                        await fail_db.commit()

    task = asyncio.create_task(_spawn())
    _RUN_TASKS[run_id] = task
    task.add_done_callback(lambda _: _RUN_TASKS.pop(run_id, None))
    return _run_dto(run)


@router.get("/runs", response_model=List[RunDTO])
async def list_runs(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EvalRun).order_by(desc(EvalRun.created_at)).limit(limit)
    )
    return [_run_dto(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}", response_model=RunDTO)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(EvalRun).filter(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_dto(run)


async def _delete_run_impl(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(EvalRun).filter(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    if run.status in {"pending", "running"}:
        await _cancel_run_task(run_id)

    result_rows = await db.execute(
        select(EvalCaseResult).filter(EvalCaseResult.run_id == run_id)
    )
    rows = result_rows.scalars().all()

    hidden_session_ids = {
        row.session_id for row in rows
        if row.session_id
    }

    if hidden_session_ids:
        session_result = await db.execute(
            alive_select(DiagnosticSession).where(
                DiagnosticSession.id.in_(hidden_session_ids),
                DiagnosticSession.is_hidden == True,
            )
        )
        sessions = session_result.scalars().all()
        alive_session_ids = [session.id for session in sessions]

        if alive_session_ids:
            message_result = await db.execute(
                alive_select(ChatMessage).where(ChatMessage.session_id.in_(alive_session_ids))
            )
            for msg in message_result.scalars().all():
                msg.soft_delete(user.id)
            for session in sessions:
                session.soft_delete(user.id)

    await db.execute(delete(EvalCaseResult).where(EvalCaseResult.run_id == run_id))
    await db.execute(delete(EvalRun).where(EvalRun.id == run_id))
    await db.commit()
    return {"message": "评测记录已删除", "run_id": run_id}


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _delete_run_impl(run_id, db, user)


@router.post("/runs/{run_id}/delete")
async def delete_run_compat(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _delete_run_impl(run_id, db, user)


@router.get("/runs/{run_id}/results", response_model=List[CaseResultSummary])
async def list_run_results(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EvalCaseResult)
        .filter(EvalCaseResult.run_id == run_id)
        .order_by(EvalCaseResult.id)
    )
    return [_result_summary(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}/results/{case_id}", response_model=CaseResultDetail)
async def get_run_result_detail(
    run_id: int,
    case_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EvalCaseResult)
        .filter(EvalCaseResult.run_id == run_id, EvalCaseResult.case_id == case_id)
        .order_by(desc(EvalCaseResult.id))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="result not found")
    return _result_detail(row)


@router.get("/runs/{run_id}/results/{case_id}/replay", response_model=EvalReplayDTO)
async def get_run_result_replay(
    run_id: int,
    case_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EvalCaseResult)
        .filter(EvalCaseResult.run_id == run_id, EvalCaseResult.case_id == case_id)
        .order_by(desc(EvalCaseResult.id))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="result not found")
    if not row.session_id:
        raise HTTPException(status_code=404, detail="replay session not found")

    session_result = await db.execute(
        select(DiagnosticSession).filter(
            DiagnosticSession.id == row.session_id,
            DiagnosticSession.is_hidden == True,
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="replay session not found")

    messages_result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.session_id == row.session_id, ChatMessage.deleted_at.is_(None))
        .order_by(ChatMessage.id)
    )
    messages = [_replay_message(message) for message in messages_result.scalars().all()]

    return EvalReplayDTO(
        run_id=run_id,
        case_id=row.case_id,
        case_title=row.case_title,
        case_category=row.case_category,
        session_id=session.id,
        session_title=session.title,
        ai_model_id=session.ai_model_id,
        input_tokens=session.input_tokens or 0,
        output_tokens=session.output_tokens or 0,
        total_tokens=session.total_tokens or 0,
        messages=messages,
    )
