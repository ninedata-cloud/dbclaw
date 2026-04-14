import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.conversation_skills import assess_tool_risk, execute_skill_call
from backend.models.action_run import ActionRun
from backend.models.datasource import Datasource
from backend.models.diagnostic_session import DiagnosticSession
from backend.models.report import Report
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.skills.registry import SkillRegistry
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_REJECTED = "rejected"
STATUS_EXECUTING = "executing"
STATUS_EXECUTION_SUCCEEDED = "execution_succeeded"
STATUS_EXECUTION_FAILED = "execution_failed"
STATUS_VERIFYING = "verifying"
STATUS_VERIFIED_PASSED = "verified_passed"
STATUS_VERIFIED_FAILED = "verified_failed"

DB_PREFIX_MAP = {
    "mysql": "mysql",
    "tdsql-c-mysql": "mysql",
    "postgresql": "pg",
    "sqlserver": "mssql",
    "oracle": "oracle",
    "opengauss": "opengauss",
}

READ_ONLY_VERIFY_SKILLS = {
    "postgresql": "pg_get_db_status",
    "mysql": "mysql_get_process_list",
    "tdsql-c-mysql": "mysql_get_process_list",
    "sqlserver": "mssql_list_connections",
    "oracle": "oracle_list_sessions",
    "opengauss": "opengauss_list_connections",
}


def _normalize_existing_actions(report: Report, verify_skill: str | None) -> list[dict[str, Any]] | None:
    actions = report.recommended_actions
    if not isinstance(actions, list) or not actions:
        return None

    changed = False
    normalized: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            normalized.append(action)
            continue

        cloned = dict(action)
        verification = cloned.get("verification")
        if verify_skill and isinstance(verification, dict) and verification.get("skill_id") != verify_skill:
            verification = {
                **verification,
                "skill_id": verify_skill,
                "params": {"datasource_id": report.datasource_id, "timeout": 90},
                "success_criteria": "验证结果返回正常，且未出现新的错误信息。",
            }
            cloned["verification"] = verification
            changed = True
        normalized.append(cloned)

    return normalized if changed else actions


def _extract_text_summary(content_md: Optional[str]) -> str:
    if not content_md:
        return ""
    for raw_line in content_md.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = line.lstrip("-•*1234567890. ")
        if len(normalized) >= 12:
            return normalized[:220]
    return ""


async def _build_default_action_spec(db: AsyncSession, report: Report) -> list[dict[str, Any]]:
    datasource = await get_alive_by_id(db, Datasource, report.datasource_id)
    db_type = datasource.db_type if datasource else None
    verify_skill = READ_ONLY_VERIFY_SKILLS.get(db_type or "")

    normalized_existing = _normalize_existing_actions(report, verify_skill)
    if normalized_existing is not None:
        if normalized_existing is not report.recommended_actions:
            report.recommended_actions = normalized_existing
            await db.commit()
            await db.refresh(report)
        return report.recommended_actions

    action_id = f"report-{report.id}-recommendation-1"
    title = report.trigger_reason or report.summary or "执行诊断建议"
    summary = _extract_text_summary(report.content_md) or report.summary or "基于巡检报告执行一次处置建议并验证结果。"

    if report.trigger_type == "connection_failure":
        if datasource:
            tool_args = {"datasource_id": report.datasource_id, "sql": "SELECT 1;"}
        else:
            tool_args = {"datasource_id": report.datasource_id, "sql": "SELECT 1;"}
        step_skill = "execute_any_sql"
        precheck = "执行前请确认 SQL 为只读或符合变更窗口要求。"
    else:
        prefix = DB_PREFIX_MAP.get(db_type or "", "pg")
        step_skill = f"{prefix}_get_db_status"
        tool_args = {"datasource_id": report.datasource_id}
        precheck = "执行前请结合当前告警状态确认是否需要人工干预。"

    risk = await assess_tool_risk(step_skill, tool_args, ["execute_any_sql", "admin"] if step_skill == "execute_any_sql" else ["execute_query"])

    verification = None
    if verify_skill:
        verification = {
            "skill_id": verify_skill,
            "params": {"datasource_id": report.datasource_id, "timeout": 90},
            "success_criteria": "验证结果返回正常，且未出现新的错误信息。",
        }

    actions = [{
        "id": action_id,
        "title": title[:120],
        "summary": summary[:220],
        "risk_level": risk["level"],
        "precheck": precheck,
        "steps": [{
            "skill_id": step_skill,
            "params": tool_args,
        }],
        "verification": verification,
        "source_ref": {
            "report_id": report.id,
            "alert_id": report.alert_id,
            "session_id": report.ai_conversation_id,
        },
    }]
    report.recommended_actions = actions
    await db.commit()
    await db.refresh(report)
    return actions


async def ensure_report_recommended_actions(db: AsyncSession, report: Report) -> list[dict[str, Any]]:
    return await _build_default_action_spec(db, report)


async def get_report_actions_with_runs(db: AsyncSession, report: Report) -> list[dict[str, Any]]:
    actions = await ensure_report_recommended_actions(db, report)

    result = await db.execute(
        select(ActionRun)
        .where(ActionRun.report_id == report.id)
        .order_by(ActionRun.created_at.desc(), ActionRun.id.desc())
    )
    runs = result.scalars().all()

    latest_map: dict[str, ActionRun] = {}
    for run in runs:
        latest_map.setdefault(run.recommendation_id, run)

    enriched = []
    for action in actions:
        latest = latest_map.get(action.get("id"))
        enriched.append({
            **action,
            "latest_run": serialize_action_run_summary(latest) if latest else None,
        })
    return enriched


async def create_action_run(
    db: AsyncSession,
    *,
    report_id: int,
    recommendation_id: str,
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
) -> ActionRun:
    report = await get_alive_by_id(db, Report, report_id)
    if not report:
        raise ValueError("报告不存在")

    actions = await ensure_report_recommended_actions(db, report)
    action = next((item for item in actions if item.get("id") == recommendation_id), None)
    if not action:
        raise ValueError("推荐动作不存在")

    session = None
    if session_id is not None:
        session = await get_alive_by_id(db, DiagnosticSession, session_id)
        if not session:
            raise ValueError("会话不存在")
    elif report.ai_conversation_id:
        session = await get_alive_by_id(db, DiagnosticSession, report.ai_conversation_id)
        session_id = session.id if session else None

    step = (action.get("steps") or [{}])[0]
    skill_id = step.get("skill_id")
    verification = action.get("verification") or {}

    run = ActionRun(
        report_id=report.id,
        alert_id=report.alert_id,
        session_id=session_id,
        datasource_id=report.datasource_id,
        recommendation_id=action.get("id"),
        title=action.get("title") or "执行推荐动作",
        risk_level=action.get("risk_level") or "safe",
        action_spec=action,
        skill_id=skill_id,
        verification_skill_id=verification.get("skill_id"),
        approval_status="not_required",
        execution_status="pending",
        verification_status="not_requested",
        status=STATUS_EXECUTING,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await execute_action_run(db, run.id, user_id=user_id)
    await db.refresh(run)

    return run


async def attach_approval_to_action_run(db: AsyncSession, run_id: int, approval_id: str) -> ActionRun:
    run = await db.get(ActionRun, run_id)
    if not run:
        raise ValueError("动作执行记录不存在")
    run.approval_id = approval_id
    run.approval_status = "pending"
    run.status = STATUS_PENDING_APPROVAL
    await db.commit()
    await db.refresh(run)
    return run


async def update_action_run_after_approval(
    db: AsyncSession,
    *,
    approval_id: str,
    action: str,
    user_id: Optional[int] = None,
) -> Optional[ActionRun]:
    result = await db.execute(select(ActionRun).where(ActionRun.approval_id == approval_id).order_by(ActionRun.id.desc()))
    run = result.scalars().first()
    if not run:
        return None

    run.approval_status = action
    if action == "approved":
        run.approved_by = user_id
        run.approved_at = now()
        run.status = STATUS_EXECUTING
    else:
        run.status = STATUS_REJECTED
    await db.commit()
    await db.refresh(run)
    return run


async def execute_action_run(db: AsyncSession, run_id: int, user_id: Optional[int] = None) -> ActionRun:
    run = await db.get(ActionRun, run_id)
    if not run:
        raise ValueError("动作执行记录不存在")

    action = run.action_spec or {}
    step = (action.get("steps") or [{}])[0]
    skill_id = step.get("skill_id") or run.skill_id
    params = dict(step.get("params") or {})
    session_id = run.session_id

    run.skill_id = skill_id
    run.status = STATUS_EXECUTING
    run.execution_status = "running"
    await db.commit()

    result_text, _, skill_execution_id, _ = await execute_skill_call(skill_id, params, db, user_id, session_id)
    run.skill_execution_id = skill_execution_id

    try:
        result_payload = json.loads(result_text)
    except Exception:
        result_payload = {"raw": result_text}

    if isinstance(result_payload, dict) and result_payload.get("error"):
        run.execution_status = "failed"
        run.status = STATUS_EXECUTION_FAILED
        run.execution_result_summary = str(result_payload.get("error"))[:500]
    else:
        run.execution_status = "succeeded"
        run.status = STATUS_EXECUTION_SUCCEEDED
        run.execution_result_summary = _extract_execution_summary(result_payload)

    await db.commit()
    await db.refresh(run)
    return run


async def verify_action_run(db: AsyncSession, run_id: int, user_id: Optional[int] = None) -> ActionRun:
    run = await db.get(ActionRun, run_id)
    if not run:
        raise ValueError("动作执行记录不存在")

    verification = (run.action_spec or {}).get("verification") or {}
    verification_skill_id = verification.get("skill_id") or run.verification_skill_id
    verification_params = dict(verification.get("params") or {})
    if not verification_skill_id:
        raise ValueError("该动作未配置验证步骤")

    run.status = STATUS_VERIFYING
    run.verification_status = "running"
    run.verification_skill_id = verification_skill_id
    await db.commit()

    result_text, _, skill_execution_id, _ = await execute_skill_call(
        verification_skill_id,
        verification_params,
        db,
        user_id,
        run.session_id,
    )
    run.verification_skill_execution_id = skill_execution_id

    try:
        result_payload = json.loads(result_text)
    except Exception:
        result_payload = {"raw": result_text}

    if isinstance(result_payload, dict) and result_payload.get("error"):
        run.verification_status = "failed"
        run.status = STATUS_VERIFIED_FAILED
        run.verification_summary = str(result_payload.get("error"))[:500]
    else:
        run.verification_status = "passed"
        run.status = STATUS_VERIFIED_PASSED
        run.verification_summary = _extract_execution_summary(result_payload)

    await db.commit()
    await db.refresh(run)
    return run


async def list_action_runs(
    db: AsyncSession,
    *,
    report_id: Optional[int] = None,
    alert_id: Optional[int] = None,
    session_id: Optional[int] = None,
    datasource_id: Optional[int] = None,
    limit: int = 50,
) -> list[ActionRun]:
    query = select(ActionRun)
    if report_id is not None:
        query = query.where(ActionRun.report_id == report_id)
    if alert_id is not None:
        query = query.where(ActionRun.alert_id == alert_id)
    if session_id is not None:
        query = query.where(ActionRun.session_id == session_id)
    if datasource_id is not None:
        query = query.where(ActionRun.datasource_id == datasource_id)
    query = query.order_by(ActionRun.created_at.desc(), ActionRun.id.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


def serialize_action_run_summary(run: Optional[ActionRun]) -> Optional[dict[str, Any]]:
    if not run:
        return None
    return {
        "run_id": run.id,
        "recommendation_id": run.recommendation_id,
        "title": run.title,
        "risk_level": run.risk_level,
        "status": run.status,
        "approval_status": run.approval_status,
        "execution_status": run.execution_status,
        "execution_result_summary": run.execution_result_summary,
        "verification_status": run.verification_status,
        "verification_summary": run.verification_summary,
        "approval_id": run.approval_id,
        "skill_id": run.skill_id,
        "skill_execution_id": run.skill_execution_id,
        "verification_skill_id": run.verification_skill_id,
        "verification_skill_execution_id": run.verification_skill_execution_id,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def serialize_action_run_detail(run: ActionRun) -> dict[str, Any]:
    return {
        **serialize_action_run_summary(run),
        "report_id": run.report_id,
        "alert_id": run.alert_id,
        "session_id": run.session_id,
        "datasource_id": run.datasource_id,
        "action_spec": run.action_spec,
        "approved_by": run.approved_by,
    }


def _extract_execution_summary(result_payload: Any) -> str:
    if isinstance(result_payload, dict):
        if result_payload.get("message"):
            return str(result_payload["message"])[:500]
        if result_payload.get("summary"):
            return str(result_payload["summary"])[:500]
        rendered = json.dumps(result_payload, ensure_ascii=False, default=str)
        return rendered[:500]
    if isinstance(result_payload, list):
        rendered = json.dumps(result_payload, ensure_ascii=False, default=str)
        return rendered[:500]
    return str(result_payload)[:500]
