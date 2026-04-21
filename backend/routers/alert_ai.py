from __future__ import annotations

from typing import Optional
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_admin, get_current_user
from backend.models.alert_ai_evaluation_log import AlertAIEvaluationLog
from backend.models.alert_ai_policy import AlertAIPolicy
from backend.models.alert_ai_runtime_state import AlertAIRuntimeState
from backend.models.datasource import Datasource
from backend.models.datasource_metric import DatasourceMetric
from backend.models.soft_delete import alive_filter
from backend.models.user import User
from backend.schemas.alert_ai import (
    AlertAIEvaluationLogResponse,
    AlertAIPolicyCreate,
    AlertAIPolicyResponse,
    AlertAIStatsResponse,
    AlertAIPolicyToggleRequest,
    AlertAIPolicyUpdate,
    AlertAIPreviewRequest,
    AlertAIPreviewResponse,
    AlertAIPreviewSample,
)
from backend.services.alert_ai_service import (
    build_alert_ai_feature_summary,
    compile_alert_ai_policy,
    compute_ai_transition,
    ensure_alert_ai_policy_compiled,
    evaluate_alert_ai_policy,
    get_ai_alert_confidence_threshold,
    resolve_alert_ai_policy_binding,
)
from backend.utils.datetime_helper import now

router = APIRouter(prefix="/api/alert-ai", tags=["alert-ai"], dependencies=[Depends(get_current_user)])


@router.get("/policies", response_model=list[AlertAIPolicyResponse])
async def list_alert_ai_policy(
    include_disabled: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    query = select(AlertAIPolicy).order_by(AlertAIPolicy.name.asc(), AlertAIPolicy.id.asc())
    if not include_disabled:
        query = query.where(AlertAIPolicy.is_enabled == True)
    result = await db.execute(query)
    policies = result.scalars().all()
    changed = False
    for policy in policies:
        before_compiled_at = getattr(policy, "compiled_at", None)
        before_status = getattr(policy, "compile_status", None)
        await ensure_alert_ai_policy_compiled(db, policy)
        if before_compiled_at != getattr(policy, "compiled_at", None) or before_status != getattr(policy, "compile_status", None):
            changed = True
    if changed:
        await db.commit()
        for policy in policies:
            await db.refresh(policy)
    return policies


@router.post("/policies", response_model=AlertAIPolicyResponse, dependencies=[Depends(get_current_admin)])
async def create_alert_ai_policy(
    data: AlertAIPolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    existing = await db.execute(select(AlertAIPolicy).where(AlertAIPolicy.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="AI 告警模板名称已存在")

    policy = AlertAIPolicy(
        name=data.name,
        description=data.description,
        rule_text=data.rule_text,
        is_enabled=data.enabled,
        model_id=data.model_id,
        analysis_strategy=data.analysis_strategy,
        analysis_config=data.analysis_config,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    await compile_alert_ai_policy(policy, db)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.put("/policies/{policy_id}", response_model=AlertAIPolicyResponse, dependencies=[Depends(get_current_admin)])
async def update_alert_ai_policy(
    policy_id: int,
    data: AlertAIPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    policy = await db.get(AlertAIPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="AI 告警模板不存在")

    if data.name and data.name != policy.name:
        existing = await db.execute(select(AlertAIPolicy).where(AlertAIPolicy.name == data.name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="AI 告警模板名称已存在")
        policy.name = data.name

    if data.description is not None:
        policy.description = data.description
    if data.rule_text is not None:
        policy.rule_text = data.rule_text
    if data.enabled is not None:
        policy.is_enabled = data.enabled
    if "model_id" in data.model_fields_set:
        policy.model_id = data.model_id
    if "analysis_strategy" in data.model_fields_set:
        policy.analysis_strategy = data.analysis_strategy
    if "analysis_config" in data.model_fields_set:
        policy.analysis_config = data.analysis_config

    policy.updated_by = current_user.id
    await compile_alert_ai_policy(policy, db)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.post("/policies/{policy_id}/toggle", response_model=AlertAIPolicyResponse, dependencies=[Depends(get_current_admin)])
async def toggle_alert_ai_policy(
    policy_id: int,
    data: AlertAIPolicyToggleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    policy = await db.get(AlertAIPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="AI 告警模板不存在")
    policy.is_enabled = data.enabled
    policy.updated_by = current_user.id
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/stats", response_model=AlertAIStatsResponse)
async def get_alert_ai_stats(
    datasource_id: Optional[int] = None,
    policy_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(AlertAIRuntimeState)
    if datasource_id is not None:
        query = query.where(AlertAIRuntimeState.datasource_id == datasource_id)
    if policy_id is not None:
        query = query.where(AlertAIRuntimeState.policy_id == policy_id)

    result = await db.execute(query)
    runtime_states = result.scalars().all()

    samples_seen = sum(int(item.samples_seen or 0) for item in runtime_states)
    candidate_hits = sum(int(item.candidate_hits or 0) for item in runtime_states)
    ai_evaluations = sum(int(item.ai_evaluations or 0) for item in runtime_states)
    gate_skips_by_reason: dict[str, int] = {}
    for item in runtime_states:
        for key, value in dict(item.gate_skips_by_reason or {}).items():
            gate_skips_by_reason[key] = gate_skips_by_reason.get(key, 0) + int(value or 0)

    log_query = select(
        func.coalesce(func.avg(AlertAIEvaluationLog.total_tokens), 0),
    ).where(AlertAIEvaluationLog.mode == "formal")
    if datasource_id is not None:
        log_query = log_query.where(AlertAIEvaluationLog.datasource_id == datasource_id)
    if policy_id is not None:
        log_query = log_query.where(AlertAIEvaluationLog.policy_id == policy_id)
    avg_tokens = int(round(float((await db.execute(log_query)).scalar() or 0)))
    skipped = max(samples_seen - ai_evaluations, 0)

    return AlertAIStatsResponse(
        samples_seen=samples_seen,
        candidate_hits=candidate_hits,
        ai_evaluations=ai_evaluations,
        gate_skips_by_reason=gate_skips_by_reason,
        token_saved_estimate=skipped * max(avg_tokens, 0),
        avg_tokens_per_evaluation=avg_tokens,
    )


def _pick_preview_snapshots(snapshots: list[DatasourceMetric], max_samples: int) -> list[DatasourceMetric]:
    if len(snapshots) <= max_samples:
        return snapshots
    if max_samples <= 1:
        return [snapshots[-1]]

    indexes = []
    last_index = len(snapshots) - 1
    for offset in range(max_samples):
        ratio = offset / (max_samples - 1)
        indexes.append(min(last_index, round(last_index * ratio)))

    seen = set()
    selected = []
    for index in indexes:
        if index in seen:
            continue
        seen.add(index)
        selected.append(snapshots[index])
    return selected


@router.post("/evaluate-preview", response_model=AlertAIPreviewResponse)
async def evaluate_alert_ai_preview(
    data: AlertAIPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    ds_result = await db.execute(
        select(Datasource).where(Datasource.id == data.datasource_id, alive_filter(Datasource))
    )
    datasource = ds_result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    binding = await resolve_alert_ai_policy_binding(
        db,
        ai_policy_source=data.ai_policy_source,
        ai_policy_text=data.ai_policy_text,
        ai_policy_id=data.ai_policy_id,
        alert_ai_model_id=data.alert_ai_model_id,
    )
    if not binding:
        raise HTTPException(status_code=400, detail="AI 告警规则未配置或模板不可用")

    result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == datasource.id,
            DatasourceMetric.metric_type == "db_status",
            DatasourceMetric.collected_at >= now() - timedelta(hours=data.hours),
        )
        .order_by(DatasourceMetric.collected_at.asc())
    )
    snapshots = result.scalars().all()
    if not snapshots:
        return AlertAIPreviewResponse(
            datasource_id=datasource.id,
            policy_source=binding.policy_source,
            policy_name=binding.display_name,
            model_id=binding.model_id,
            sample_count=0,
            alert_count=0,
            recover_count=0,
            samples=[],
        )

    sampled_snapshots = _pick_preview_snapshots(snapshots, data.max_samples)
    runtime_state = AlertAIRuntimeState(
        datasource_id=datasource.id,
        policy_id=binding.policy_id,
        policy_source=binding.policy_source,
        policy_fingerprint=binding.policy_fingerprint,
        is_active=False,
        consecutive_alert_count=0,
        consecutive_recover_count=0,
    )
    confidence_threshold = await get_ai_alert_confidence_threshold(db)
    alert_count = 0
    recover_count = 0
    samples: list[AlertAIPreviewSample] = []

    for snapshot in sampled_snapshots:
        feature_summary = await build_alert_ai_feature_summary(
            db,
            datasource,
            binding.rule_text,
            snapshot.data or {},
            snapshot.collected_at,
            compiled_trigger_profile=binding.compiled_trigger_profile,
            runtime_state=runtime_state,
        )
        judge_result, log_entry = await evaluate_alert_ai_policy(
            db,
            datasource,
            binding,
            feature_summary,
            runtime_state,
            mode="preview",
        )
        transition = compute_ai_transition(
            active=bool(runtime_state.is_active),
            decision=judge_result.decision,
            confidence=judge_result.confidence,
            confidence_threshold=confidence_threshold,
            consecutive_alert_count=runtime_state.consecutive_alert_count or 0,
            consecutive_recover_count=runtime_state.consecutive_recover_count or 0,
            cooldown_until=runtime_state.cooldown_until,
            current_time=snapshot.collected_at,
        )
        action = transition.action if not judge_result.error_message else "noop"
        if action == "trigger_alert":
            alert_count += 1
        elif action == "recover_alert":
            recover_count += 1

        runtime_state.is_active = transition.active
        runtime_state.consecutive_alert_count = transition.consecutive_alert_count
        runtime_state.consecutive_recover_count = transition.consecutive_recover_count
        runtime_state.cooldown_until = transition.cooldown_until
        runtime_state.last_decision = judge_result.decision
        runtime_state.last_confidence = judge_result.confidence
        runtime_state.last_reason = judge_result.reason
        runtime_state.last_evaluated_at = snapshot.collected_at
        if action == "trigger_alert":
            runtime_state.last_triggered_at = snapshot.collected_at
        elif action == "recover_alert":
            runtime_state.last_recovered_at = snapshot.collected_at

        log_entry.is_accepted = action in {"trigger_alert", "recover_alert"}

        samples.append(
            AlertAIPreviewSample(
                snapshot_id=snapshot.id,
                collected_at=snapshot.collected_at,
                decision=judge_result.decision,
                confidence=judge_result.confidence,
                severity=judge_result.severity,
                policy_severity_hint=judge_result.policy_severity_hint,
                severity_source=judge_result.severity_source,
                reason=judge_result.reason,
                evidence=judge_result.evidence,
                accepted=log_entry.is_accepted,
                action=action,
            )
        )

    await db.commit()
    return AlertAIPreviewResponse(
        datasource_id=datasource.id,
        policy_source=binding.policy_source,
        policy_name=binding.display_name,
        model_id=binding.model_id,
        sample_count=len(samples),
        alert_count=alert_count,
        recover_count=recover_count,
        samples=samples,
    )


@router.get("/evaluations", response_model=dict)
async def list_alert_ai_evaluations(
    datasource_id: Optional[int] = None,
    policy_id: Optional[int] = None,
    mode: Optional[str] = Query(None, pattern="^(formal|shadow|preview)$"),
    decision: Optional[str] = Query(None, pattern="^(alert|no_alert|recover)$"),
    status: Optional[str] = Query(None, pattern="^(accepted|recorded|failed)$"),
    keyword: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(AlertAIEvaluationLog)
    count_query = select(func.count(AlertAIEvaluationLog.id))

    if datasource_id is not None:
        query = query.where(AlertAIEvaluationLog.datasource_id == datasource_id)
        count_query = count_query.where(AlertAIEvaluationLog.datasource_id == datasource_id)
    if policy_id is not None:
        query = query.where(AlertAIEvaluationLog.policy_id == policy_id)
        count_query = count_query.where(AlertAIEvaluationLog.policy_id == policy_id)
    if mode:
        query = query.where(AlertAIEvaluationLog.mode == mode)
        count_query = count_query.where(AlertAIEvaluationLog.mode == mode)
    if decision:
        query = query.where(AlertAIEvaluationLog.decision == decision)
        count_query = count_query.where(AlertAIEvaluationLog.decision == decision)
    if status == "accepted":
        status_clause = AlertAIEvaluationLog.is_accepted == True
    elif status == "recorded":
        status_clause = and_(
            AlertAIEvaluationLog.is_accepted == False,
            AlertAIEvaluationLog.error_message.is_(None),
        )
    elif status == "failed":
        status_clause = AlertAIEvaluationLog.error_message.is_not(None)
    else:
        status_clause = None

    if status_clause is not None:
        query = query.where(status_clause)
        count_query = count_query.where(status_clause)

    if keyword and keyword.strip():
        search = f"%{keyword.strip()}%"
        keyword_clause = or_(
            AlertAIEvaluationLog.reason.ilike(search),
            AlertAIEvaluationLog.error_message.ilike(search),
            AlertAIEvaluationLog.decision.ilike(search),
            AlertAIEvaluationLog.severity.ilike(search),
            AlertAIEvaluationLog.policy_severity_hint.ilike(search),
            AlertAIEvaluationLog.mode.ilike(search),
        )
        query = query.where(keyword_clause)
        count_query = count_query.where(keyword_clause)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(AlertAIEvaluationLog.created_at.desc(), AlertAIEvaluationLog.id.desc()).limit(limit).offset(offset)
    )
    logs = result.scalars().all()
    datasource_ids = sorted({item.datasource_id for item in logs if item.datasource_id is not None})
    datasource_name_map: dict[int, str] = {}
    if datasource_ids:
        datasource_result = await db.execute(
            select(Datasource.id, Datasource.name).where(
                Datasource.id.in_(datasource_ids),
                alive_filter(Datasource),
            )
        )
        datasource_name_map = {row.id: row.name for row in datasource_result}

    return {
        "items": [
            AlertAIEvaluationLogResponse.model_validate({
                **item.__dict__,
                "datasource_name": datasource_name_map.get(item.datasource_id),
            })
            for item in logs
        ],
        "total": total,
    }
