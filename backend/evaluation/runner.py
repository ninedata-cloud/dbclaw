"""Evaluation runner — drives a single case or a whole suite end-to-end."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import select

from backend.agent.conversation_skills import run_conversation_with_skills
from backend.agent.tool_override import reset_tool_override, set_tool_override
from backend.evaluation.case_loader import EvalCase, get_case
from backend.evaluation.judge import run_judge
from backend.evaluation.mock_executor import CallRecorder, make_mock_override
from backend.evaluation.scorer import (
    WEIGHT_ACTION,
    WEIGHT_ROOT_CAUSE,
    combine_scores,
    compute_programmatic,
)
from backend.models.ai_model import AIModel
from backend.models.diagnostic_session import DiagnosticSession
from backend.models.evaluation import EvalCaseResult, EvalRun
from backend.routers.ai_models import decrypt_api_key
from backend.services.ai_agent import get_ai_client

logger = logging.getLogger(__name__)


@dataclass
class CaseRunOutput:
    case_id: str
    status: str                  # "completed" | "failed"
    score: float
    dimension_scores: List[Dict[str, Any]]
    judge_feedback: Dict[str, Any]
    tool_call_summary: Dict[str, Any]
    conclusion_md: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    session_id: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------- helpers

def _extract_conclusion_md(content_chunks: List[str]) -> str:
    """Concatenate the streamed AI content into a final conclusion document."""
    return "".join(content_chunks).strip()


async def _resolve_ai_client(db, model_id: Optional[int]):
    if model_id:
        result = await db.execute(select(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True))
        model = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(AIModel)
            .filter(AIModel.is_active == True)
            .order_by(AIModel.is_default.desc(), AIModel.id.asc())
        )
        model = result.scalars().first()
    if not model:
        return None, None
    client = get_ai_client(
        api_key=decrypt_api_key(model.api_key_encrypted),
        base_url=model.base_url,
        model_name=model.model_name,
        protocol=getattr(model, "protocol", "openai"),
        reasoning_effort=getattr(model, "reasoning_effort", None),
    )
    return client, model


# ---------------------------------------------------------------- core

async def run_case(
    case: EvalCase,
    db,
    ai_model_id: Optional[int],
    user_id: Optional[int],
    judge_model_id: Optional[int] = None,
    on_session_created: Optional[Callable[[int], Awaitable[None]]] = None,
) -> CaseRunOutput:
    """Run a single case: create shadow session → drive AI with mock tools → score."""
    start = time.time()

    # 1. shadow DiagnosticSession (hidden)
    session = DiagnosticSession(
        user_id=user_id,
        datasource_id=None,
        host_id=None,
        title=f"[eval] {case.id}",
        ai_model_id=ai_model_id,
        is_hidden=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    if on_session_created:
        await on_session_created(session.id)

    recorder = CallRecorder()
    override = make_mock_override(case, recorder)
    token = set_tool_override(override)

    content_chunks: List[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    error: Optional[str] = None

    try:
        messages = [{"role": "user", "content": case.user_message}]
        async for event in run_conversation_with_skills(
            messages=messages,
            datasource_id=None,
            model_id=ai_model_id,
            db=db,
            user_id=user_id,
            session_id=session.id,
            skip_approval=True,           # never gate during eval
            context_override=case.context.to_dict(),
        ):
            etype = event.get("type")
            if etype == "content":
                content_chunks.append(event.get("content", ""))
            elif etype == "done":
                final = event.get("content")
                if final and not content_chunks:
                    content_chunks.append(final)
            elif etype == "usage":
                usage = event.get("usage") or {}
                prompt_tokens += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                completion_tokens += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            elif etype == "error":
                error = event.get("message") or "unknown_error"
                break
    except Exception as exc:
        logger.exception("run_case %s failed", case.id)
        error = f"{type(exc).__name__}: {exc}"
    finally:
        reset_tool_override(token)

    latency_ms = int((time.time() - start) * 1000)
    conclusion_md = _extract_conclusion_md(content_chunks)

    # 2. judge (LLM-as-judge) — runs even on partial failure if we have any text
    judge_client = None
    judge_model_obj = None
    if not error or conclusion_md:
        judge_client, judge_model_obj = await _resolve_ai_client(db, judge_model_id)
    if judge_client is not None:
        judge_result = await run_judge(case, conclusion_md, judge_client)
    else:
        from backend.evaluation.judge import JudgeResult
        judge_result = JudgeResult(
            root_cause_score=0.0,
            action_score=0.0,
            root_cause_feedback="",
            action_feedback="",
            error="no_judge_client_available",
        )

    # 3. programmatic dimensions + combine
    programmatic = compute_programmatic(case, recorder, conclusion_md, latency_ms)
    total, dim_dicts = combine_scores(
        programmatic,
        judge_result.root_cause_score,
        judge_result.action_score,
    )

    tool_summary = {
        "called": [
            {
                "tool": c.tool_name,
                "args": c.args,
                "matched": c.matched,
                "kind": c.kind,
                "argument_valid": c.argument_valid,
                "argument_errors": c.argument_errors,
            }
            for c in recorder.calls
        ],
        "missing_required": programmatic.missing_required_tools,
        "forbidden_hits": programmatic.forbidden_tool_hits,
        "unmatched_count": recorder.unmatched_count(),
        "invalid_argument_count": recorder.invalid_argument_count(),
    }

    judge_feedback = judge_result.to_dict()

    if error:
        status = "failed" if not conclusion_md else "completed"
    else:
        status = "completed"

    return CaseRunOutput(
        case_id=case.id,
        status=status,
        score=total,
        dimension_scores=dim_dicts,
        judge_feedback=judge_feedback,
        tool_call_summary=tool_summary,
        conclusion_md=conclusion_md,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        session_id=session.id,
        error=error,
    )


# ---------------------------------------------------------------- suite runner

async def execute_run(
    run_id: int,
    db,
    case_ids: List[str],
    ai_model_id: Optional[int],
    judge_model_id: Optional[int],
    user_id: Optional[int],
    concurrency: int = 1,
):
    """Drive an EvalRun: load each case, run it, persist EvalCaseResult, update aggregates.

    Concurrency defaults to 1 because LLM provider rate limits are tighter than
    DB capacity — caller can bump this.
    """
    run_result = await db.execute(select(EvalRun).filter(EvalRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise RuntimeError(f"EvalRun {run_id} not found")

    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.total_cases = len(case_ids)
    run.completed_cases = 0
    run.failed_cases = 0
    await db.commit()

    sem = asyncio.Semaphore(max(1, concurrency))
    scores: List[float] = []
    dim_totals: Dict[str, float] = {}
    dim_counts: Dict[str, int] = {}

    async def _run_one(cid: str) -> None:
        case = get_case(cid)
        if not case:
            row = EvalCaseResult(
                run_id=run_id,
                case_id=cid,
                status="failed",
                error_message=f"case not found: {cid}",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
            db.add(row)
            await db.commit()
            run.failed_cases += 1
            await db.commit()
            return

        async with sem:
            row = EvalCaseResult(
                run_id=run_id,
                case_id=cid,
                case_title=case.title,
                case_category=case.category,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)

            try:
                async def _attach_session(session_id: int) -> None:
                    row.session_id = session_id
                    await db.commit()

                output = await run_case(
                    case,
                    db,
                    ai_model_id,
                    user_id,
                    judge_model_id,
                    on_session_created=_attach_session,
                )
            except Exception as exc:
                logger.exception("case %s crashed", cid)
                row.status = "failed"
                row.error_message = f"{type(exc).__name__}: {exc}"
                row.finished_at = datetime.now(timezone.utc)
                await db.commit()
                run.failed_cases += 1
                await db.commit()
                return

            row.status = output.status
            row.score = output.score
            row.dimension_scores = output.dimension_scores
            row.judge_feedback = output.judge_feedback
            row.tool_call_summary = output.tool_call_summary
            row.conclusion_md = output.conclusion_md
            row.latency_ms = output.latency_ms
            row.prompt_tokens = output.prompt_tokens
            row.completion_tokens = output.completion_tokens
            row.total_tokens = output.total_tokens
            row.session_id = output.session_id
            row.error_message = output.error
            row.finished_at = datetime.now(timezone.utc)
            await db.commit()

            scores.append(float(output.score))
            for d in output.dimension_scores:
                name = d["name"]
                dim_totals[name] = dim_totals.get(name, 0.0) + float(d["score"])
                dim_counts[name] = dim_counts.get(name, 0) + 1

            if output.status == "failed":
                run.failed_cases += 1
            run.completed_cases += 1
            await db.commit()

    # NOTE: we run cases sequentially when concurrency=1 to avoid SQLAlchemy
    # async session contention. Concurrent execution would need per-task sessions.
    if concurrency <= 1:
        for cid in case_ids:
            await _run_one(cid)
    else:
        await asyncio.gather(*[_run_one(c) for c in case_ids])

    if scores:
        run.total_score = round(sum(scores) / len(scores), 2)
    run.dimension_summary = {
        name: round(dim_totals[name] / dim_counts[name], 2)
        for name in dim_totals
    }
    run.status = "completed" if run.failed_cases < run.total_cases else "failed"
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()
