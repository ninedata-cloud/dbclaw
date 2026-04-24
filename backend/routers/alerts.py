from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import html
escape_html = html.escape
import hashlib
import logging

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.services.alert_service import AlertService
from backend.services.alert_service import build_alert_display_metric_name, build_alert_display_title
from backend.services.alert_event_service import AlertEventService
from backend.services.notification_service import NotificationService
from backend.services.public_share_service import PublicShareService
from backend.config import get_settings
from backend.models.report import Report
from backend.models.datasource import Datasource
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.datasource_metric import DatasourceMetric
from backend.models.alert_message import AlertMessage
from backend.services.alert_event_service import hydrate_event_strategy_fields
from backend.services.baseline_service import (
    compute_upper_bound,
    extract_metric_value,
    get_profiles_for_slot,
)
from sqlalchemy import select
from backend.schemas.alert import (
    AlertMessageResponse,
    AlertDiagnosisContext,
    AlertBaselineComparisonItem,
    AlertDatasourceInfo,
    AlertLinkedReport,
    AlertQueryParams,
    AlertAcknowledgeRequest,
    AlertResolveRequest,
    AlertSubscriptionCreate,
    AlertSubscriptionUpdate,
    AlertSubscriptionResponse,
    TestNotificationRequest,
    AlertEventResponse,
    AlertEventQueryParams,
    AlertEventAcknowledgeRequest
)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
logger = logging.getLogger(__name__)


def _extract_recommended_action(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        normalized = line.lstrip("-•*1234567890. ")
        if any(keyword in normalized for keyword in ["建议", "处置", "操作", "下一步", "优化"]):
            return normalized[:220]
    return None


def _build_datasource_info(datasource: Optional[Datasource]) -> Optional[AlertDatasourceInfo]:
    if not datasource:
        return None

    return AlertDatasourceInfo(
        id=datasource.id,
        name=datasource.name,
        db_type=datasource.db_type,
        host=datasource.host,
        port=datasource.port,
        database=datasource.database,
        importance_level=datasource.importance_level or 'production',
        remark=datasource.remark,
        connection_status=datasource.connection_status or 'unknown',
        connection_error=datasource.connection_error,
    )


async def _build_event_baseline_comparisons(db: AsyncSession, event) -> list[AlertBaselineComparisonItem]:
    snapshot_result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == event.datasource_id,
            DatasourceMetric.metric_type == "db_status",
        )
        .order_by(DatasourceMetric.collected_at.desc())
        .limit(1)
    )
    latest_snapshot = snapshot_result.scalar_one_or_none()
    if not latest_snapshot or not isinstance(latest_snapshot.data, dict):
        return []

    metric_names: list[str] = []
    if event.metric_name:
        metric_names.append(event.metric_name)

    alerts_result = await db.execute(
        select(AlertMessage.metric_name)
        .where(AlertMessage.event_id == event.id, AlertMessage.metric_name.isnot(None))
        .distinct()
    )
    for metric_name in alerts_result.scalars().all():
        if metric_name and metric_name not in metric_names:
            metric_names.append(metric_name)

    if not metric_names and getattr(event, "fault_domain", None) == "performance":
        metric_names = ["cpu_usage", "disk_usage", "connections"]
    if not metric_names:
        return []

    profiles = await get_profiles_for_slot(
        db,
        datasource_id=event.datasource_id,
        collected_at=latest_snapshot.collected_at,
        metric_names=metric_names,
    )
    comparisons: list[AlertBaselineComparisonItem] = []
    for metric_name in metric_names[:6]:
        profile = profiles.get(metric_name)
        current_value = extract_metric_value(latest_snapshot.data, metric_name)
        if current_value is None:
            continue

        upper_bound = compute_upper_bound(profile, {}) if profile else None
        status = "no_profile"
        deviation_ratio = None
        if profile and upper_bound:
            status = "above_baseline" if current_value > upper_bound else "within_baseline"
            base = float(profile.p95_value or profile.avg_value or 0)
            if base > 0:
                deviation_ratio = round(float(current_value) / base, 4)

        comparisons.append(
            AlertBaselineComparisonItem(
                metric_name=metric_name,
                current_value=round(float(current_value), 4),
                baseline_avg=getattr(profile, "avg_value", None),
                baseline_p95=getattr(profile, "p95_value", None),
                upper_bound=upper_bound,
                deviation_ratio=deviation_ratio,
                sample_count=int(getattr(profile, "sample_count", 0) or 0),
                status=status,
                slot_label=f"周{latest_snapshot.collected_at.weekday() + 1} {latest_snapshot.collected_at.hour:02d}:00",
            )
        )
    return comparisons


def _resolve_subscription_user_id(requested_user_id: Optional[int], current_user: User) -> int:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user.id
    if current_user.is_admin:
        return requested_user_id
    raise HTTPException(status_code=403, detail="不能访问其他用户的订阅")


async def _get_subscription_for_user(db: AsyncSession, subscription_id: int, current_user: User):
    from backend.models.alert_subscription import AlertSubscription

    subscription = await get_alive_by_id(db, AlertSubscription, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if not current_user.is_admin and subscription.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="不能操作其他用户的订阅")
    return subscription


async def _build_alert_response(db: AsyncSession, alert) -> AlertMessageResponse:
    datasource = await get_alive_by_id(db, Datasource, alert.datasource_id)

    report_result = await db.execute(
        select(Report)
        .where(Report.alert_id == alert.id, alive_filter(Report))
        .order_by(Report.created_at.desc())
        .limit(1)
    )
    report = report_result.scalar_one_or_none()

    if not report and alert.event_id:
        event_alerts_result = await db.execute(
            select(Report)
            .where(
                Report.datasource_id == alert.datasource_id,
                Report.trigger_type.in_(["anomaly", "connection_failure"]),
                alive_filter(Report),
            )
            .order_by(Report.created_at.desc())
            .limit(1)
        )
        report = event_alerts_result.scalar_one_or_none()

    trigger_result = await db.execute(
        select(InspectionTrigger)
        .where(InspectionTrigger.alert_id == alert.id)
        .order_by(InspectionTrigger.triggered_at.desc())
        .limit(1)
    )
    trigger = trigger_result.scalar_one_or_none()

    # Fetch root_cause from alert event if available
    root_cause = None
    diagnosis_summary = None
    if alert.event_id:
        from backend.models.alert_event import AlertEvent
        event_result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert.event_id))
        event_obj = event_result.scalar_one_or_none()
        if event_obj:
            root_cause = event_obj.root_cause
            # Use event root_cause as diagnosis_summary if no report summary
            if not diagnosis_summary and event_obj.ai_diagnosis_summary:
                diagnosis_summary = event_obj.ai_diagnosis_summary

    case_summary = alert.trigger_reason or alert.content.split("\n")[0] if alert.content else None
    if not diagnosis_summary:
        diagnosis_summary = report.summary if report else None
    recommended_action = _extract_recommended_action(report.content_md if report else None)
    diagnosis_entry_hash = None

    linked_report = None
    if report:
        linked_report = AlertLinkedReport(
            report_id=report.id,
            title=report.title,
            status=report.status,
            trigger_type=report.trigger_type,
            created_at=report.created_at,
            summary=report.summary,
        )
        diagnosis_entry_hash = hashlib.md5(f"alert:{alert.id}:report:{report.id}".encode("utf-8")).hexdigest()[:12]

    datasource_info = _build_datasource_info(datasource)

    payload = AlertMessageResponse.model_validate(alert)
    payload.title = build_alert_display_title(
        alert_type=payload.alert_type,
        title=payload.title,
        metric_name=payload.metric_name,
        trigger_reason=payload.trigger_reason,
    )
    payload.metric_name = build_alert_display_metric_name(
        alert_type=payload.alert_type,
        metric_name=payload.metric_name,
        trigger_reason=payload.trigger_reason,
    )
    payload.diagnosis_context = AlertDiagnosisContext(
        datasource_name=datasource.name if datasource else None,
        datasource_type=datasource.db_type if datasource else None,
        datasource_info=datasource_info,
        case_summary=case_summary,
        diagnosis_summary=diagnosis_summary,
        root_cause=root_cause,
        recommended_action=recommended_action,
        latest_trigger_type=(trigger.trigger_type if trigger else (report.trigger_type if report else None)),
        linked_report=linked_report,
        diagnosis_entry_hash=diagnosis_entry_hash,
    )
    return payload


async def _load_latest_alert_trigger_reasons(db: AsyncSession, events) -> dict[int, Optional[str]]:
    latest_alert_ids = [int(event.latest_alert_id) for event in events if getattr(event, "latest_alert_id", None)]
    if not latest_alert_ids:
        return {}

    result = await db.execute(
        select(AlertMessage.id, AlertMessage.trigger_reason)
        .where(AlertMessage.id.in_(latest_alert_ids))
    )
    return {int(alert_id): trigger_reason for alert_id, trigger_reason in result.all()}


def _build_event_response(event, datasource=None, latest_trigger_reason: Optional[str] = None) -> AlertEventResponse:
    payload = AlertEventResponse.model_validate(event)
    payload.title = build_alert_display_title(
        alert_type=payload.alert_type,
        title=payload.title,
        metric_name=payload.metric_name,
        trigger_reason=latest_trigger_reason,
        fault_domain=payload.fault_domain,
    )
    payload.metric_name = build_alert_display_metric_name(
        alert_type=payload.alert_type,
        metric_name=payload.metric_name,
        trigger_reason=latest_trigger_reason,
        fault_domain=payload.fault_domain,
    )
    # Add datasource silence information
    if datasource:
        payload.datasource_silence_until = datasource.silence_until
        payload.datasource_silence_reason = datasource.silence_reason
    return payload


async def _build_event_context(db: AsyncSession, event) -> AlertDiagnosisContext:
    hydrate_event_strategy_fields(event)
    datasource = await get_alive_by_id(db, Datasource, event.datasource_id)
    datasource_info = _build_datasource_info(datasource)
    recommended_action = _extract_recommended_action(event.recommended_actions or event.ai_diagnosis_summary)
    baseline_comparisons = await _build_event_baseline_comparisons(db, event)
    latest_alert = await db.get(AlertMessage, event.latest_alert_id) if getattr(event, "latest_alert_id", None) else None
    display_title = build_alert_display_title(
        alert_type=getattr(event, "alert_type", None),
        title=getattr(event, "title", None),
        metric_name=getattr(event, "metric_name", None),
        trigger_reason=getattr(latest_alert, "trigger_reason", None),
        fault_domain=getattr(event, "fault_domain", None),
    )
    return AlertDiagnosisContext(
        datasource_name=datasource.name if datasource else None,
        datasource_type=datasource.db_type if datasource else None,
        datasource_info=datasource_info,
        case_summary=display_title,
        diagnosis_summary=event.ai_diagnosis_summary,
        root_cause=event.root_cause,
        recommended_action=recommended_action or event.recommended_actions,
        latest_trigger_type=event.alert_type or event.metric_name,
        event_category=event.event_category,
        fault_domain=event.fault_domain,
        lifecycle_stage=event.lifecycle_stage,
        is_diagnosis_refresh_needed=event.is_diagnosis_refresh_needed,
        diagnosis_trigger_reason=event.diagnosis_trigger_reason,
        baseline_comparisons=baseline_comparisons,
    )


@router.get("", response_model=dict)
async def list_alerts(
    datasource_ids: Optional[str] = Query(None, description="Comma-separated datasource IDs"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    status: Optional[str] = Query("all", pattern="^(active|acknowledged|resolved|all)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List alerts with filters"""
    # Parse datasource_ids
    datasource_id_list = None
    if datasource_ids:
        try:
            datasource_id_list = [int(x.strip()) for x in datasource_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datasource_ids format")

    params = AlertQueryParams(
        datasource_ids=datasource_id_list,
        start_time=start_time,
        end_time=end_time,
        status=status,
        severity=severity,
        search=search,
        limit=limit,
        offset=offset
    )

    alerts, total = await AlertService.get_alerts(db, params)

    return {
        "alerts": [await _build_alert_response(db, alert) for alert in alerts],
        "total": total,
        "limit": limit,
        "offset": offset
    }


# Alert Event Endpoints (must be before /{alert_id} to avoid route conflicts)
@router.get("/events", response_model=dict)
async def list_alert_event(
    datasource_ids: Optional[str] = Query(None, description="Comma-separated datasource IDs"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    status: Optional[str] = Query("all", pattern="^(active|acknowledged|resolved|all)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query(None, description="Sort field"),
    sort_order: Optional[str] = Query(None, pattern="^(asc|desc)$", description="Sort order"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List aggregated alert events with filters"""
    # Parse datasource_ids
    datasource_id_list = None
    if datasource_ids:
        try:
            datasource_id_list = [int(x.strip()) for x in datasource_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datasource_ids format")

    events_with_datasource, total = await AlertEventService.get_events(
        db=db,
        datasource_ids=datasource_id_list,
        start_time=start_time,
        end_time=end_time,
        status=status,
        severity=severity,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset
    )

    # Extract events for loading trigger reasons
    events = [event for event, _ in events_with_datasource]
    latest_trigger_reason_map = await _load_latest_alert_trigger_reasons(db, events)

    return {
        "events": [
            _build_event_response(event, datasource, latest_trigger_reason_map.get(getattr(event, "latest_alert_id", 0)))
            for event, datasource in events_with_datasource
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/events/{event_id}/alerts", response_model=dict)
async def get_event_alerts(
    event_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get all alerts in an event"""
    alerts, total = await AlertEventService.get_alerts_in_event(
        db=db,
        event_id=event_id,
        limit=limit,
        offset=offset
    )

    return {
        "alerts": [await _build_alert_response(db, alert) for alert in alerts],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/events/{event_id}/acknowledge", response_model=AlertEventResponse)
async def acknowledge_event(
    event_id: int,
    request: AlertEventAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acknowledge event and all its alerts"""
    try:
        del request
        event = await AlertEventService.acknowledge_event(db, event_id, current_user.id)
        latest_alert = await db.get(AlertMessage, event.latest_alert_id) if getattr(event, "latest_alert_id", None) else None
        datasource = await get_alive_by_id(db, Datasource, event.datasource_id) if event.datasource_id else None
        await db.commit()
        return _build_event_response(event, datasource, getattr(latest_alert, "trigger_reason", None))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise


@router.post("/events/{event_id}/resolve", response_model=AlertEventResponse)
async def resolve_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Resolve event and all its alerts"""
    try:
        event = await AlertEventService.resolve_event(db, event_id)
        latest_alert = await db.get(AlertMessage, event.latest_alert_id) if getattr(event, "latest_alert_id", None) else None
        datasource = await get_alive_by_id(db, Datasource, event.datasource_id) if event.datasource_id else None
        await db.commit()
        return _build_event_response(event, datasource, getattr(latest_alert, "trigger_reason", None))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise


@router.get("/events/{event_id}/context", response_model=AlertDiagnosisContext)
async def get_event_context(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    from backend.models.alert_event import AlertEvent

    result = await db.execute(select(AlertEvent).where(AlertEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return await _build_event_context(db, event)


@router.get("/{alert_id}", response_model=AlertMessageResponse)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get alert details"""
    alert = await AlertService.get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return await _build_alert_response(db, alert)


@router.get("/public/{alert_id}")
async def get_public_alert(
    alert_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get alert details with public share token"""
    PublicShareService.verify_alert_share_token(token, alert_id)
    alert = await PublicShareService.get_alert_or_404(db, alert_id)

    result = await db.execute(
        select(Report).where(Report.alert_id == alert_id, alive_filter(Report)).order_by(Report.created_at.desc()).limit(1)
    )
    report = result.scalar_one_or_none()

    payload = (await _build_alert_response(db, alert)).model_dump()
    payload["linked_report"] = None
    if report:
        report_token = PublicShareService.create_report_share_token(report.id, get_settings().public_share_expire_minutes)
        payload["linked_report"] = {
            "report_id": report.id,
            "title": report.title,
            "status": report.status,
            "share_url": f"/api/inspections/report/public/{report.id}?token={report_token}",
            "page_url": f"/api/inspections/report/public/{report.id}/page?token={report_token}"
        }

    return payload


@router.get("/{alert_id}/context", response_model=AlertDiagnosisContext)
async def get_alert_context(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get compact diagnosis context for P0 alert->report->chat loop"""
    alert = await AlertService.get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    response = await _build_alert_response(db, alert)
    return response.diagnosis_context or AlertDiagnosisContext()


@router.get("/public/{alert_id}/page", response_class=HTMLResponse)
async def public_alert_page(
    alert_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Render public alert detail page with datasource config and AI diagnosis"""
    PublicShareService.verify_alert_share_token(token, alert_id)
    alert = await PublicShareService.get_alert_or_404(db, alert_id)

    # Fetch datasource info
    datasource = await get_alive_by_id(db, Datasource, alert.datasource_id)

    # Fetch alert event for AI diagnosis
    alert_event = None
    ai_summary = None
    ai_root_cause = None
    ai_actions = None
    if alert.event_id:
        from backend.models.alert_event import AlertEvent
        result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert.event_id))
        alert_event = result.scalar_one_or_none()
        if alert_event:
            ai_summary = alert_event.ai_diagnosis_summary
            ai_root_cause = alert_event.root_cause
            ai_actions = alert_event.recommended_actions

    # Fetch linked report
    result = await db.execute(
        select(Report).where(Report.alert_id == alert_id, alive_filter(Report)).order_by(Report.created_at.desc()).limit(1)
    )
    report = result.scalar_one_or_none()

    # Severity badge
    sev = alert.severity or ''
    sev_color = {'critical': '#dc2626', 'high': '#ea580c', 'medium': '#ca8a04', 'low': '#16a34a'}.get(sev.lower(), '#6b7280')
    sev_label = {'critical': '严重', 'high': '高', 'medium': '中', 'low': '低'}.get(sev.lower(), sev)
    severity_badge = f'<span class="sev-badge" style="background:{sev_color};color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;font-weight:600;">{escape_html(sev_label)}</span>'

    # Status label
    status_label = {'active': '活跃', 'acknowledged': '已确认', 'resolved': '已解决'}.get(alert.status or '', alert.status or '-')
    status_color = {'active': '#dc2626', 'acknowledged': '#ea580c', 'resolved': '#16a34a'}.get(alert.status or '', '#6b7280')

    # Alert type label
    alert_type_label = {'threshold_violation': '超过阈值', 'baseline_deviation': '偏离基线', 'custom_expression': '自定义表达式', 'system_error': '系统错误', 'ai_policy_violation': '智能判定异常'}.get(alert.alert_type or '', alert.alert_type or '-')

    # Datasource info
    ds_name = escape_html(datasource.name if datasource else '-')
    ds_type = escape_html(datasource.db_type.upper() if datasource and datasource.db_type else '-')
    ds_host = escape_html(datasource.host if datasource else '-')
    ds_port = datasource.port if datasource else '-'
    ds_db = escape_html(datasource.database if datasource and datasource.database else '-')
    ds_level = datasource.importance_level if datasource else 'production'
    ds_level_label = {'core': '核心', 'production': '生产', 'development': '开发', 'temporary': '临时'}.get(ds_level, ds_level)
    ds_level_color = {'core': '#dc2626', 'production': '#2563eb', 'development': '#7c3aed', 'temporary': '#6b7280'}.get(ds_level, '#6b7280')
    ds_remark = escape_html(datasource.remark if datasource and datasource.remark else '')
    ds_status = datasource.connection_status if datasource else 'unknown'
    ds_status_label = {'normal': '正常', 'warning': '警告', 'failed': '失败', 'unknown': '未知'}.get(ds_status, ds_status)
    ds_status_color = {'normal': '#16a34a', 'warning': '#ca8a04', 'failed': '#dc2626', 'unknown': '#6b7280'}.get(ds_status, '#6b7280')

    # AI diagnosis sections
    has_diagnosis = ai_root_cause or ai_actions
    ai_diagnosis_html = ''
    if has_diagnosis:
        root_cause_block = f'<div class="diag-block root-cause"><div class="diag-label">🔍 根本原因</div><div class="diag-content">{escape_html(ai_root_cause)}</div></div>' if ai_root_cause else ''
        actions_block = f'<div class="diag-block actions"><div class="diag-label">🛠 建议措施</div><div class="diag-content">{escape_html(ai_actions)}</div></div>' if ai_actions else ''
        ai_diagnosis_html = f'''
        <div class="section ai-section">
            <div class="section-header">
                <span class="section-icon">🧠</span>
                <span class="section-title">AI 诊断分析</span>
            </div>
            <div class="section-body">
                {root_cause_block}
                {actions_block}
            </div>
        </div>'''

    # Report link
    report_html = ''
    if report:
        report_token = PublicShareService.create_report_share_token(report.id, get_settings().public_share_expire_minutes)
        report_status_label = {'pending': '待处理', 'running': '生成中', 'completed': '已完成', 'failed': '失败'}.get(report.status or '', report.status or '-')
        report_html = f'''
        <div class="section report-section">
            <div class="section-header">
                <span class="section-icon">📋</span>
                <span class="section-title">关联诊断报告</span>
            </div>
            <div class="section-body">
                <div class="report-info">
                    <div class="report-meta">
                        <span class="report-time">{report.created_at}</span>
                        <span class="report-title">{escape_html(report.title or f"报告 #{report.id}")}</span>
                        <span class="report-status">{report_status_label}</span>
                    </div>
                    <a class="btn btn-secondary" href="/api/inspections/report/public/{report.id}/page?token={report_token}">查看报告</a>
                </div>
            </div>
        </div>'''

    # Render markdown content
    content_md = alert.content or ''
    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt("commonmark", {"breaks": True, "html": True})
        md.enable('table')
        content_html = md.render(content_md)
    except Exception:
        content_html = f"<pre>{escape_html(content_md)}</pre>"

    return f"""
    <!DOCTYPE html>
    <html lang=\"zh-CN\">
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>{escape_html(alert.title)} - 告警详情</title>
        <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/github-markdown@2.10.0/github-markdown.min.css\">
        <style>
            :root {{
                --bg: #f5f7fa;
                --card-bg: #fff;
                --border: #e5e7eb;
                --text-primary: #1f2937;
                --text-secondary: #6b7280;
                --accent-blue: #2563eb;
                --accent-green: #16a34a;
                --accent-orange: #ea580c;
                --accent-red: #dc2626;
                --accent-yellow: #ca8a04;
            }}
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); margin:0; padding:24px; color:var(--text-primary); }}
            .container {{ max-width:1000px; margin:0 auto; }}
            .page-title {{ font-size:20px; font-weight:700; margin-bottom:20px; color:var(--text-primary); }}
            .section {{ background:var(--card-bg); border-radius:12px; padding:20px; margin-bottom:16px; box-shadow:0 2px 8px rgba(0,0,0,.06); border:1px solid var(--border); }}
            .section-header {{ display:flex; align-items:center; gap:10px; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid var(--border); }}
            .section-icon {{ font-size:18px; }}
            .section-title {{ font-size:15px; font-weight:600; color:var(--text-primary); }}
            .section-body {{ display:flex; flex-direction:column; gap:12px; }}
            .grid-2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; }}
            .grid-3 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
            .field {{ background:#f9fafb; border-radius:8px; padding:12px; }}
            .field-label {{ font-size:11px; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }}
            .field-value {{ font-size:14px; font-weight:500; color:var(--text-primary); word-break:break-word; }}
            .field-value.full {{ grid-column:1/-1; }}
            .status-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
            .remark-block {{ background:#fffbeb; border-left:3px solid #f59e0b; border-radius:4px; padding:10px 12px; margin-top:8px; }}
            .remark-label {{ font-size:11px; color:#b45309; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }}
            .remark-content {{ font-size:13px; color:#92400e; }}
            .diag-block {{ background:#f9fafb; border-radius:8px; padding:12px; }}
            .diag-block.root-cause {{ background:#fef2f2; border:1px solid #fca5a5; }}
            .diag-block.actions {{ background:#fff7ed; border:1px solid #fed7aa; }}
            .diag-label {{ font-size:11px; font-weight:600; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }}
            .diag-content {{ font-size:13px; color:var(--text-primary); line-height:1.6; white-space:pre-wrap; word-break:break-word; }}
            .report-info {{ display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
            .report-meta {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
            .report-time {{ font-size:12px; color:var(--text-secondary); }}
            .report-title {{ font-size:14px; font-weight:500; color:var(--text-primary); }}
            .report-status {{ font-size:11px; background:#f3f4f6; padding:2px 8px; border-radius:4px; color:var(--text-secondary); }}
            .content-block {{ background:#fff; border-radius:8px; padding:16px; }}
            .btn {{ display:inline-block; padding:8px 16px; border-radius:8px; text-decoration:none; font-size:13px; font-weight:500; border:none; cursor:pointer; transition:all .2s; }}
            .btn-secondary {{ background:#374151; color:#fff; }}
            .btn-secondary:hover {{ background:#4b5563; }}
            .meta-row {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; margin-bottom:16px; }}
            .meta-item {{ font-size:13px; color:var(--text-secondary); }}
            .alert-title {{ font-size:18px; font-weight:700; color:var(--text-primary); margin:0 0 16px 0; }}
            .trigger-block {{ background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:12px; margin-bottom:16px; font-size:13px; color:#1e40af; }}
            .markdown-body {{ font-size:14px; line-height:1.7; color:var(--text-primary); }}
            .markdown-body h1,.markdown-body h2,.markdown-body h3,.markdown-body h4 {{ margin-top:16px; margin-bottom:8px; font-weight:600; }}
            .markdown-body h1 {{ font-size:18px; }}
            .markdown-body h2 {{ font-size:16px; }}
            .markdown-body h3 {{ font-size:15px; }}
            .markdown-body p {{ margin:0 0 12px 0; }}
            .markdown-body code {{ background:#f3f4f6; padding:2px 6px; border-radius:4px; font-size:13px; font-family:'JetBrains Mono','Fira Code',monospace; }}
            .markdown-body pre {{ background:#1f2937; color:#e5e7eb; padding:12px; border-radius:8px; overflow-x:auto; }}
            .markdown-body pre code {{ background:none; padding:0; color:inherit; }}
            .markdown-body table {{ border-collapse:collapse; width:100%; margin:12px 0; }}
            .markdown-body th,.markdown-body td {{ border:1px solid var(--border); padding:8px 12px; text-align:left; }}
            .markdown-body th {{ background:#f9fafb; font-weight:600; }}
            .markdown-body ul,.markdown-body ol {{ margin:0 0 12px 0; padding-left:24px; }}
            .markdown-body li {{ margin-bottom:4px; }}
            @media (max-width:640px) {{
                body {{ padding:16px; }}
                .grid-2, .grid-3 {{ grid-template-columns:1fr; }}
                .report-info {{ flex-direction:column; align-items:flex-start; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="alert-title">{escape_html(alert.title)}</h1>

            <div class="meta-row">
                <span class="meta-item">{severity_badge}</span>
                <span class="meta-item" style="color:{status_color};font-weight:500;">● {status_label}</span>
                <span class="meta-item">触发时间：{alert.created_at}</span>
            </div>

            {f'<div class="trigger-block">触发原因：{escape_html(alert.trigger_reason)}</div>' if alert.trigger_reason else ''}

            <!-- 数据库配置信息 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">📊</span>
                    <span class="section-title">数据库配置信息</span>
                </div>
                <div class="section-body">
                    <div class="grid-2">
                        <div class="field">
                            <div class="field-label">名称</div>
                            <div class="field-value">{ds_name}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">类型</div>
                            <div class="field-value">{ds_type}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">连接</div>
                            <div class="field-value">{ds_host}:{ds_port} / {ds_db}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">等级</div>
                            <div class="field-value">
                                <span style="display:inline-flex;align-items:center;gap:4px;">
                                    <span class="status-dot" style="background:{ds_level_color};"></span>
                                    {ds_level_label}
                                </span>
                            </div>
                        </div>
                        <div class="field">
                            <div class="field-label">连接状态</div>
                            <div class="field-value">
                                <span style="display:inline-flex;align-items:center;gap:4px;">
                                    <span class="status-dot" style="background:{ds_status_color};"></span>
                                    {ds_status_label}
                                </span>
                            </div>
                        </div>
                    </div>
                    {f'<div class="remark-block"><div class="remark-label">备注</div><div class="remark-content">{ds_remark}</div></div>' if ds_remark else ''}
                </div>
            </div>

            <!-- 告警详情 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">⚠️</span>
                    <span class="section-title">告警详情</span>
                </div>
                <div class="section-body">
                    <div class="grid-3">
                        <div class="field">
                            <div class="field-label">告警类型</div>
                            <div class="field-value">{alert_type_label}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">指标名称</div>
                            <div class="field-value">{escape_html(alert.metric_name or '-')}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">当前值</div>
                            <div class="field-value">{'{:.2f}'.format(alert.metric_value) if alert.metric_value is not None else '-'}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">阈值</div>
                            <div class="field-value">{'{:.2f}'.format(alert.threshold_value) if alert.threshold_value is not None else '-'}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">确认时间</div>
                            <div class="field-value">{alert.acknowledged_at or '-'}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">恢复时间</div>
                            <div class="field-value">{alert.resolved_at or '-'}</div>
                        </div>
                    </div>
                </div>
            </div>

            {ai_diagnosis_html}
            {report_html}

            <!-- 详细内容 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">📝</span>
                    <span class="section-title">详细内容</span>
                </div>
                <div class="content-block markdown-body">{content_html}</div>
            </div>
        </div>
    </body>
    </html>
    """


@router.post("/{alert_id}/acknowledge", response_model=AlertMessageResponse)
async def acknowledge_alert(
    alert_id: int,
    request: AlertAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acknowledge an alert"""
    del request
    alert = await AlertService.acknowledge_alert(db, alert_id, current_user.id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return await _build_alert_response(db, alert)


@router.post("/{alert_id}/resolve", response_model=AlertMessageResponse)
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Resolve an alert"""
    alert = await AlertService.resolve_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return await _build_alert_response(db, alert)


@router.get("/subscriptions/list", response_model=List[AlertSubscriptionResponse])
async def list_subscriptions(
    user_id: Optional[int] = Query(None, description="User ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user subscriptions"""
    target_user_id = _resolve_subscription_user_id(user_id, current_user)
    subscriptions = await AlertService.get_user_subscriptions(db, target_user_id)
    return [AlertSubscriptionResponse.model_validate(sub) for sub in subscriptions]


@router.post("/subscriptions", response_model=AlertSubscriptionResponse)
async def create_subscription(
    subscription: AlertSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new alert subscription"""
    owner_user_id = _resolve_subscription_user_id(subscription.user_id, current_user)
    created = await AlertService.create_subscription(
        db,
        subscription.model_copy(update={"user_id": owner_user_id}),
    )
    return AlertSubscriptionResponse.model_validate(created)


@router.put("/subscriptions/{subscription_id}", response_model=AlertSubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    update_data: AlertSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an alert subscription"""
    await _get_subscription_for_user(db, subscription_id, current_user)
    updated = await AlertService.update_subscription(
        db,
        subscription_id,
        update_data.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return AlertSubscriptionResponse.model_validate(updated)


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an alert subscription"""
    success = await AlertService.delete_subscription(db, subscription_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return {"message": "Subscription deleted successfully"}


@router.post("/subscriptions/{subscription_id}/test")
async def test_notification(
    subscription_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test notification delivery for a subscription"""
    subscription = await _get_subscription_for_user(db, subscription_id, current_user)

    # Create a test alert
    test_alert = await AlertService.create_alert(
        db=db,
        datasource_id=subscription.datasource_ids[0] if subscription.datasource_ids else 1,
        alert_type="system_error",
        severity="low",
        metric_name="test",
        metric_value=0.0,
        threshold_value=0.0,
        trigger_reason="Test notification"
    )

    # Send notifications
    delivery_logs = await NotificationService.send_notifications(
        db, test_alert, subscription
    )

    return {
        "message": "Test notification sent",
        "alert_id": test_alert.id,
        "deliveries": [
            {
                "channel": log.channel,
                "recipient": log.recipient,
                "status": log.status,
                "error_message": log.error_message
            }
            for log in delivery_logs
        ]
    }
