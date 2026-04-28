"""API endpoints for database intelligent inspection"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
import logging

from backend.database import get_db
from backend.utils.security import escape_html
from backend.utils.datetime_helper import now, to_utc_isoformat
from backend.models.inspection_config import InspectionConfig
from backend.models.alert_template import AlertTemplate
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.report import Report
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.services.inspection_service import InspectionService
from backend.services.public_share_service import PublicShareService
from backend.services.baseline_service import (
    DEFAULT_BASELINE_CONFIG,
    list_baseline_profiles_for_datasource,
    normalize_baseline_config,
    rebuild_baseline_profiles_for_datasource,
)
from backend.services.alert_service import DEFAULT_EVENT_AI_CONFIG, normalize_event_ai_config
from backend.services.alert_template_service import (
    ensure_default_alert_template,
    get_default_alert_template,
    normalize_alert_template_config,
    reset_inspection_config_to_template,
    resolve_effective_inspection_config,
    summarize_alert_template_config,
)
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


from datetime import datetime

TERMINAL_REPORT_STATUSES = {"completed", "partial", "timed_out", "awaiting_confirm", "failed"}


def _is_terminal_report_status(status: Optional[str]) -> bool:
    return status in TERMINAL_REPORT_STATUSES


async def _ensure_report_completed_at(db: AsyncSession, report: Report) -> bool:
    if report.completed_at is not None or not _is_terminal_report_status(report.status):
        return False

    # Historical report may be missing terminal timestamps; backfill with created_at
    # so the detail page can render a stable completion time instead of a blank slot.
    report.completed_at = report.created_at or now()
    await db.commit()
    await db.refresh(report)
    return True


async def _build_report_detail_payload(
    db: AsyncSession,
    report: Report,
) -> dict:
    completed_at_inferred = await _ensure_report_completed_at(db, report)
    datasource = await get_alive_by_id(db, Datasource, report.datasource_id)

    duration_seconds = None
    if report.created_at and report.completed_at and not completed_at_inferred:
        duration_delta = int((report.completed_at - report.created_at).total_seconds())
        if duration_delta > 0:
            duration_seconds = duration_delta

    return {
        "id": report.id,
        "datasource_id": report.datasource_id,
        "datasource_name": datasource.name if datasource else None,
        "title": report.title,
        "summary": report.summary,
        "trigger_type": report.trigger_type,
        "trigger_reason": report.trigger_reason,
        "content_md": report.content_md,
        "status": report.status,
        "error_message": report.error_message,
        "alert_id": report.alert_id,
        "actions": [],
        "created_at": to_utc_isoformat(report.created_at),
        "completed_at": to_utc_isoformat(report.completed_at),
        "completed_at_inferred": completed_at_inferred,
        "duration_seconds": duration_seconds,
    }


def _normalize_inspection_config_record(config: InspectionConfig) -> InspectionConfig:
    config.baseline_config = normalize_baseline_config(getattr(config, "baseline_config", None))
    config.event_ai_config = normalize_event_ai_config(getattr(config, "event_ai_config", None))
    return config


class InspectionConfigSchema(BaseModel):
    enabled: bool
    schedule_interval: int
    use_ai_analysis: bool
    ai_model_id: Optional[int] = None
    kb_ids: List[int] = []
    alert_template_id: Optional[int] = None
    threshold_rules: dict = Field(default_factory=dict)
    alert_engine_mode: str = Field(default="inherit", pattern="^(inherit|threshold|ai)$")
    ai_policy_source: str = Field(default="inline", pattern="^(inline|template)$")
    ai_policy_text: Optional[str] = None
    ai_policy_id: Optional[int] = None
    alert_ai_model_id: Optional[int] = None
    ai_shadow_enabled: bool = False
    baseline_config: dict = Field(default_factory=dict)
    event_ai_config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ai_policy(self):
        if self.alert_template_id:
            self.ai_policy_text = (self.ai_policy_text or "").strip() or None
            return self
        if self.ai_policy_source == "template" and self.ai_policy_id is None and self.alert_engine_mode == "ai":
            raise ValueError("旧版 AI 模板模式必须提供 ai_policy_id")
        if self.ai_policy_source == "inline" and self.alert_engine_mode == "ai":
            if not (self.ai_policy_text or "").strip():
                raise ValueError("AI 告警模式下必须填写自然语言规则")
        self.ai_policy_text = (self.ai_policy_text or "").strip() or None
        return self


class InspectionConfigResponse(BaseModel):
    id: int
    datasource_id: int
    enabled: bool
    schedule_interval: int
    use_ai_analysis: bool
    ai_model_id: Optional[int] = None
    kb_ids: List[int] = []
    alert_template_id: Optional[int] = None
    alert_template_name: Optional[str] = None
    uses_template: bool = False
    template_summary: Optional[str] = None
    threshold_rules: dict
    alert_engine_mode: str = "inherit"
    ai_policy_source: str = "inline"
    ai_policy_text: Optional[str] = None
    ai_policy_id: Optional[int] = None
    alert_ai_model_id: Optional[int] = None
    ai_shadow_enabled: bool = False
    baseline_config: dict = Field(default_factory=dict)
    event_ai_config: dict = Field(default_factory=dict)
    last_scheduled_at: Optional[datetime] = None
    next_scheduled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TriggerResponse(BaseModel):
    trigger_id: int
    report_id: Optional[int] = None


class ReportListItem(BaseModel):
    report_id: int
    title: str
    trigger_type: Optional[str]
    trigger_reason: Optional[str]
    created_at: str
    status: str
    error_message: Optional[str] = None


class ExpressionValidationRequest(BaseModel):
    expression: str


class ExpressionValidationResponse(BaseModel):
    valid: bool
    error: Optional[str] = None


class BaselineProfileResponse(BaseModel):
    metric_name: str
    weekday: int
    hour: int
    sample_count: int
    avg_value: Optional[float] = None
    p95_value: Optional[float] = None
    max_value: Optional[float] = None
    last_snapshot_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BaselineSummaryResponse(BaseModel):
    enabled: bool
    baseline_config: dict
    profile_count: int
    last_profile_updated_at: Optional[datetime] = None
    profiles: List[BaselineProfileResponse] = Field(default_factory=list)
    diagnostics: dict = Field(default_factory=dict)


class AlertTemplateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    template_config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_template_config(self):
        normalized = normalize_alert_template_config(self.template_config)
        if normalized.get("alert_engine_mode") == "ai" and not normalized.get("ai_policy_text"):
            raise ValueError("AI 判警模板必须提供自然语言规则")
        self.name = self.name.strip()
        self.description = (self.description or "").strip() or None
        self.template_config = normalized
        return self


class AlertTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    enabled: bool
    is_default: bool
    template_config: dict
    summary: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _build_alert_template_response(template: AlertTemplate) -> AlertTemplateResponse:
    normalized = normalize_alert_template_config(template.template_config)
    return AlertTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        enabled=template.enabled,
        is_default=template.is_default,
        template_config=normalized,
        summary=summarize_alert_template_config(normalized),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


async def _get_bound_alert_template_or_raise(db: AsyncSession, template_id: Optional[int]) -> Optional[AlertTemplate]:
    if not template_id:
        return None
    result = await db.execute(select(AlertTemplate).where(AlertTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="告警模板不存在")
    if not template.enabled:
        raise HTTPException(status_code=400, detail="告警模板已停用，请选择其他模板")
    return template


@router.post("/validate-expression", response_model=ExpressionValidationResponse)
async def validate_threshold_expression(request: ExpressionValidationRequest):
    """Test if expression is valid Python syntax"""
    try:
        # Try to compile the expression
        compile(request.expression, '<string>', 'eval')
        return ExpressionValidationResponse(valid=True, error=None)
    except SyntaxError as e:
        return ExpressionValidationResponse(valid=False, error=str(e))
    except Exception as e:
        logger.error(f"Failed to validate expression '{request.expression}': {e}", exc_info=True)
        return ExpressionValidationResponse(valid=False, error=f"Validation error: {str(e)}")


@router.get("/templates", response_model=List[AlertTemplateResponse])
async def list_alert_template(db: AsyncSession = Depends(get_db)):
    await ensure_default_alert_template(db)
    result = await db.execute(select(AlertTemplate).order_by(AlertTemplate.is_default.desc(), AlertTemplate.name.asc()))
    return [_build_alert_template_response(item) for item in result.scalars().all()]


@router.post("/templates", response_model=AlertTemplateResponse)
async def create_alert_template(data: AlertTemplateSchema, db: AsyncSession = Depends(get_db)):
    await ensure_default_alert_template(db)
    if data.is_default:
        result = await db.execute(select(AlertTemplate))
        for item in result.scalars().all():
            item.is_default = False

    template = AlertTemplate(
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        is_default=data.is_default,
        template_config=data.template_config,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return _build_alert_template_response(template)


@router.put("/templates/{template_id}", response_model=AlertTemplateResponse)
async def update_alert_template(template_id: int, data: AlertTemplateSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertTemplate).where(AlertTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if data.is_default:
        all_result = await db.execute(select(AlertTemplate))
        for item in all_result.scalars().all():
            item.is_default = False

    template.name = data.name
    template.description = data.description
    template.enabled = data.enabled
    template.is_default = data.is_default
    template.template_config = data.template_config
    await db.commit()
    await db.refresh(template)
    return _build_alert_template_response(template)


@router.post("/templates/{template_id}/toggle", response_model=AlertTemplateResponse)
async def toggle_alert_template(template_id: int, enabled: bool = Body(..., embed=True), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertTemplate).where(AlertTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    template.enabled = bool(enabled)
    await db.commit()
    await db.refresh(template)
    return _build_alert_template_response(template)


@router.get("/config/{datasource_id}", response_model=InspectionConfigResponse)
async def get_config(datasource_id: int, db: AsyncSession = Depends(get_db)):
    """Get inspection configuration for a datasource"""
    await ensure_default_alert_template(db)
    default_template = await get_default_alert_template(db)
    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        # Create default config
        config = InspectionConfig(
            datasource_id=datasource_id,
            enabled=False,
            schedule_interval=86400,
            use_ai_analysis=True,
            alert_template_id=default_template.id if default_template else None,
            threshold_rules={},
            alert_engine_mode="inherit",
            ai_policy_source="inline",
            ai_shadow_enabled=False,
            baseline_config=normalize_baseline_config(DEFAULT_BASELINE_CONFIG),
            event_ai_config=normalize_event_ai_config(DEFAULT_EVENT_AI_CONFIG),
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    elif default_template and not getattr(config, "alert_template_id", None):
        # Historical records may not be bound to any template. In that case,
        # bind once to the current default template. Do not overwrite explicit
        # user bindings on read; otherwise GET /config would silently revert
        # runtime thresholds back to default values.
        if reset_inspection_config_to_template(config, default_template):
            await db.commit()
            await db.refresh(config)
    effective = await resolve_effective_inspection_config(db, _normalize_inspection_config_record(config))
    return InspectionConfigResponse(
        id=config.id,
        datasource_id=config.datasource_id,
        enabled=config.is_enabled,
        schedule_interval=config.schedule_interval,
        use_ai_analysis=config.use_ai_analysis,
        ai_model_id=config.ai_model_id,
        kb_ids=config.kb_ids or [],
        alert_template_id=effective.alert_template_id,
        alert_template_name=effective.alert_template_name,
        uses_template=effective.uses_template,
        template_summary=effective.template_summary,
        threshold_rules=effective.threshold_rules,
        alert_engine_mode=effective.alert_engine_mode,
        ai_policy_source=effective.ai_policy_source,
        ai_policy_text=effective.ai_policy_text,
        ai_policy_id=effective.ai_policy_id,
        alert_ai_model_id=effective.alert_ai_model_id,
        ai_shadow_enabled=effective.ai_shadow_enabled,
        baseline_config=effective.baseline_config,
        event_ai_config=effective.event_ai_config,
        last_scheduled_at=config.last_scheduled_at,
        next_scheduled_at=config.next_scheduled_at,
    )


@router.post("/config/{datasource_id}", response_model=InspectionConfigResponse)
async def create_or_update_config(
    datasource_id: int,
    config_data: InspectionConfigSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create or update inspection configuration"""
    await _get_bound_alert_template_or_raise(db, config_data.alert_template_id)
    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()

    from datetime import timedelta
    from backend.utils.datetime_helper import now as get_now
    if config:
        payload = config_data.model_dump()
        payload["baseline_config"] = normalize_baseline_config(payload.get("baseline_config"))
        payload["event_ai_config"] = normalize_event_ai_config(payload.get("event_ai_config"))
        for key, value in payload.items():
            setattr(config, key, value)
        # Recalculate next_scheduled_at based on new interval
        config.next_scheduled_at = get_now() + timedelta(seconds=config_data.schedule_interval)
    else:
        payload = config_data.model_dump()
        payload["baseline_config"] = normalize_baseline_config(payload.get("baseline_config"))
        payload["event_ai_config"] = normalize_event_ai_config(payload.get("event_ai_config"))
        config = InspectionConfig(datasource_id=datasource_id, **payload)
        config.next_scheduled_at = get_now() + timedelta(seconds=config_data.schedule_interval)
        db.add(config)

    await db.commit()
    await db.refresh(config)
    return await get_config(datasource_id, db)


@router.put("/config/{datasource_id}", response_model=InspectionConfigResponse)
async def update_config(
    datasource_id: int,
    config_data: InspectionConfigSchema,
    db: AsyncSession = Depends(get_db)
):
    """Update inspection configuration"""
    await _get_bound_alert_template_or_raise(db, config_data.alert_template_id)
    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    from datetime import timedelta
    from backend.utils.datetime_helper import now as get_now
    payload = config_data.model_dump()
    payload["baseline_config"] = normalize_baseline_config(payload.get("baseline_config"))
    payload["event_ai_config"] = normalize_event_ai_config(payload.get("event_ai_config"))
    for key, value in payload.items():
        setattr(config, key, value)
    # Recalculate next_scheduled_at based on new interval
    config.next_scheduled_at = get_now() + timedelta(seconds=config_data.schedule_interval)

    await db.commit()
    await db.refresh(config)
    return await get_config(datasource_id, db)


@router.get("/baseline/{datasource_id}", response_model=BaselineSummaryResponse)
async def get_baseline_summary(
    datasource_id: int,
    limit: int = Query(default=24, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = config_result.scalar_one_or_none()
    effective = await resolve_effective_inspection_config(db, config) if config else None
    baseline_config = normalize_baseline_config(getattr(effective, "baseline_config", None) if effective else None)
    profiles = await list_baseline_profiles_for_datasource(db, datasource_id, limit=limit)
    last_profile_updated_at = max((profile.updated_at for profile in profiles if profile.updated_at), default=None)
    return BaselineSummaryResponse(
        enabled=bool(baseline_config.get("enabled")),
        baseline_config=baseline_config,
        profile_count=len(profiles),
        last_profile_updated_at=last_profile_updated_at,
        profiles=[BaselineProfileResponse.model_validate(profile) for profile in profiles[:limit]],
        diagnostics={
            "learning_days": baseline_config.get("learning_days"),
            "min_samples": baseline_config.get("min_samples"),
            "default_metrics": [name for name, item in baseline_config.get("metrics", {}).items() if item.get("enabled")],
        },
    )


@router.post("/baseline/{datasource_id}/rebuild", response_model=dict)
async def rebuild_baseline(datasource_id: int, db: AsyncSession = Depends(get_db)):
    config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    effective = await resolve_effective_inspection_config(db, config)
    baseline_config = normalize_baseline_config(getattr(effective, "baseline_config", None))
    result = await rebuild_baseline_profiles_for_datasource(
        db,
        datasource_id=datasource_id,
        baseline_config=baseline_config,
    )
    profiles = await list_baseline_profiles_for_datasource(db, datasource_id)
    return {
        "message": "baseline rebuilt",
        "result": result,
        "profile_count": len(profiles),
    }


@router.post("/trigger/{datasource_id}", response_model=TriggerResponse)
async def trigger_manual_inspection(
    datasource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger an inspection"""
    from backend.services import metric_collector
    inspection_service = metric_collector._inspection_service

    if not inspection_service:
        raise HTTPException(status_code=503, detail="Inspection service not available")

    trigger_id = await inspection_service.trigger_inspection(
        db, datasource_id, "manual", "人工触发巡检"
    )
    return TriggerResponse(trigger_id=trigger_id, report_id=None)


@router.get("/reports", response_model=dict)
async def list_all_report(
    datasource_id: Optional[int] = None,
    trigger_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List all inspection report with filters"""
    from backend.models.datasource import Datasource

    query = select(Report, Datasource.name.label('datasource_name')).join(
        Datasource, and_(Report.datasource_id == Datasource.id, alive_filter(Datasource)), isouter=True
    ).where(alive_filter(Report))

    if datasource_id:
        query = query.where(Report.datasource_id == datasource_id)
    if trigger_type:
        query = query.where(Report.trigger_type == trigger_type)
    if status:
        query = query.where(Report.status == status)
    if start_date:
        query = query.where(Report.created_at >= start_date)
    if end_date:
        query = query.where(Report.created_at <= end_date)

    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(Report).where(alive_filter(Report))
    if datasource_id:
        count_query = count_query.where(Report.datasource_id == datasource_id)
    if trigger_type:
        count_query = count_query.where(Report.trigger_type == trigger_type)
    if status:
        count_query = count_query.where(Report.status == status)
    if start_date:
        count_query = count_query.where(Report.created_at >= start_date)
    if end_date:
        count_query = count_query.where(Report.created_at <= end_date)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Report.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    rows = result.all()

    report = [
        {
            "report_id": row.Report.id,
            "datasource_name": row.datasource_name,
            "title": row.Report.title,
            "trigger_type": row.Report.trigger_type,
            "trigger_reason": row.Report.trigger_reason,
            "created_at": to_utc_isoformat(row.Report.created_at) or "",
            "status": row.Report.status,
            "error_message": row.Report.error_message
        }
        for row in rows
    ]

    return {"report": report, "total": total}


@router.get("/reports/{datasource_id}", response_model=List[ReportListItem])
async def list_report(
    datasource_id: int,
    trigger_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """List inspection report for a datasource"""
    query = select(Report).where(Report.datasource_id == datasource_id, alive_filter(Report))

    if trigger_type:
        query = query.where(Report.trigger_type == trigger_type)

    query = query.order_by(Report.created_at.desc()).limit(limit)

    result = await db.execute(query)
    report = result.scalars().all()

    return [
        ReportListItem(
            report_id=r.id,
            title=r.title,
            trigger_type=r.trigger_type,
            trigger_reason=r.trigger_reason,
            created_at=to_utc_isoformat(r.created_at) or "",
            status=r.status,
            error_message=r.error_message
        )
        for r in report
    ]


@router.get("/reports/detail/{report_id}")
async def get_report_detail(report_id: int, db: AsyncSession = Depends(get_db)):
    """Get full report details"""
    report = await get_alive_by_id(db, Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    return await _build_report_detail_payload(db, report)


@router.get("/reports/public/{report_id}")
async def get_public_report_detail(
    report_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get report details with public share token"""
    PublicShareService.verify_report_share_token(token, report_id)
    report = await PublicShareService.get_report_or_404(db, report_id)
    return await _build_report_detail_payload(db, report)


@router.get("/reports/public/{report_id}/page", response_class=HTMLResponse)
async def public_report_page(
    report_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Render public report detail page with datasource config and AI diagnosis"""
    PublicShareService.verify_report_share_token(token, report_id)
    report = await PublicShareService.get_report_or_404(db, report_id)
    await _ensure_report_completed_at(db, report)

    # Fetch datasource info
    datasource = await get_alive_by_id(db, Datasource, report.datasource_id)
    ds_host = datasource.host if datasource else '-'
    ds_port = datasource.port if datasource else '-'
    ds_db = datasource.database if datasource else '-'
    ds_remark = datasource.remark if datasource else ''
    ds_level = datasource.importance_level if datasource else '-'
    ds_tags = ', '.join(datasource.tags) if datasource and datasource.tags else '-'

    # Fetch alert event for AI diagnosis
    alert_event = None
    ai_summary = None
    ai_root_cause = None
    ai_actions = None
    if report.alert_id:
        from backend.models.alert_event import AlertEvent
        result = await db.execute(select(AlertEvent).where(AlertEvent.id == report.alert_id))
        alert_event = result.scalar_one_or_none()
        if alert_event:
            ai_summary = alert_event.ai_diagnosis_summary
            ai_root_cause = alert_event.root_cause
            ai_actions = alert_event.recommended_actions
    # Fallback to report summary fields
    if not ai_summary and report.summary:
        ai_summary = report.summary
    if not ai_root_cause and report.trigger_reason:
        ai_root_cause = report.trigger_reason

    # Escape HTML in datasource fields
    ds_name = escape_html(datasource.name if datasource else '-')
    ds_type = escape_html(datasource.db_type if datasource else '-')
    ds_host_esc = escape_html(ds_host)
    ds_db_esc = escape_html(ds_db)
    ds_remark_esc = escape_html(ds_remark)
    ds_level_esc = escape_html(ds_level)
    ds_tags_esc = escape_html(ds_tags)

    severity_badge = ''
    if alert_event:
        sev = alert_event.severity or ''
        sev_color = {'critical': '#dc2626', 'high': '#ea580c', 'medium': '#ca8a04', 'low': '#16a34a'}.get(sev.lower(), '#6b7280')
        severity_badge = '<span style="background:' + sev_color + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">' + escape_html(sev.upper()) + '</span>'

    report_html = report.content_html or f"<pre>{report.content_md or '暂无内容'}</pre>"
    return f"""
    <!DOCTYPE html>
    <html lang=\"zh-CN\">
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>{escape_html(report.title)}</title>
        <style>
                        body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f5f7fa; margin:0; padding:24px; color:#1f2937; }}
                        .card {{ max-width:1200px; margin:0 auto; background:#fff; border-radius:12px; padding:24px; box-shadow:0 8px 24px rgba(0,0,0,.08); }}
                        .meta {{ display:flex; gap:16px; flex-wrap:wrap; color:#6b7280; margin-bottom:20px; }}
                        .trigger {{ background:#eff6ff; color:#1d4ed8; padding:12px 14px; border-radius:8px; margin-bottom:20px; }}
                        .ds-card {{ background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px; padding:16px 20px; margin-bottom:20px; }}
                        .ds-title {{ font-size:16px; font-weight:600; margin-bottom:12px; display:flex; align-items:center; gap:10px; }}
                        .ds-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }}
                        .ds-field {{ background:#fff; border-radius:6px; padding:8px 12px; }}
                        .ds-label {{ font-size:11px; color:#9ca3af; text-transform:uppercase; letter-spacing:.5px; margin-bottom:3px; }}
                        .ds-value {{ font-size:13px; font-weight:500; color:#374151; }}
                        .ds-remark {{ margin-top:12px; padding:10px 12px; background:#fffbeb; border-left:3px solid #f59e0b; border-radius:4px; font-size:13px; color:#92400e; }}
                        .ds-remark-label {{ font-size:11px; color:#b45309; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }}
                        .ai-card {{ background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; padding:16px 20px; margin-bottom:20px; }}
                        .ai-title {{ font-size:15px; font-weight:600; color:#166534; margin-bottom:12px; display:flex; align-items:center; gap:8px; }}
                        .ai-section {{ margin-bottom:12px; }}
                        .ai-label {{ font-size:11px; color:#6b7280; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }}
                        .ai-value {{ font-size:13px; color:#1f2937; white-space:pre-wrap; word-break:break-word; background:#fff; border-radius:6px; padding:10px 12px; border:1px solid #e5e7eb; }}
                        .ai-value.root-cause {{ border-color:#fca5a5; background:#fef2f2; }}
                        .ai-value.actions {{ border-color:#fed7aa; background:#fff7ed; }}
        </style>
    </head>
    <body>
        <div class=\"card\">
            <h1>{escape_html(report.title)}</h1>
            <div class=\"meta\">
                <span>状态：{escape_html(report.status)}</span>
                <span>触发类型：{escape_html(report.trigger_type or '-')}</span>
                <span>创建时间：{report.created_at}</span>
                {severity_badge}
            </div>
            {f'<div class="trigger">触发原因：{escape_html(report.trigger_reason)}</div>' if report.trigger_reason else ''}

            <!-- 数据源配置信息 -->
            <div class="ds-card">
                <div class="ds-title">
                    <span>&#128202;</span> 数据源配置
                </div>
                <div class="ds-grid">
                    <div class="ds-field"><div class="ds-label">名称</div><div class="ds-value">{ds_name}</div></div>
                    <div class="ds-field"><div class="ds-label">类型</div><div class="ds-value">{ds_type.upper()}</div></div>
                    <div class="ds-field"><div class="ds-label">主机</div><div class="ds-value">{ds_host_esc}:{ds_port}</div></div>
                    <div class="ds-field"><div class="ds-label">数据库</div><div class="ds-value">{ds_db_esc or "-"}</div></div>
                    <div class="ds-field"><div class="ds-label">重要等级</div><div class="ds-value">{ds_level_esc}</div></div>
                    <div class="ds-field"><div class="ds-label">标签</div><div class="ds-value">{ds_tags_esc}</div></div>
                </div>
                {f'<div class="ds-remark"><div class="ds-remark-label">备注</div>{ds_remark_esc}</div>' if ds_remark else ''}
            </div>

            <!-- AI 诊断信息 -->
            {"".join([
                '<div class="ai-card">'
                + '<div class="ai-title"><span>&#129514;</span> AI 诊断结论</div>'
                + ('<div class="ai-section"><div class="ai-label">诊断摘要</div><div class="ai-value">' + escape_html(ai_summary) + '</div></div>' if ai_summary else '')
                + ('<div class="ai-section"><div class="ai-label">根因分析</div><div class="ai-value root-cause">' + escape_html(ai_root_cause) + '</div></div>' if ai_root_cause else '')
                + ('<div class="ai-section"><div class="ai-label">建议措施</div><div class="ai-value actions">' + escape_html(ai_actions) + '</div></div>' if ai_actions else '')
                + '</div>'
            ]) if (ai_summary or ai_root_cause or ai_actions) else ''}

            <!-- 报告正文 -->
            {report_html}
        </div>
    </body>
    </html>
    """




@router.get("/reports/export/{report_id}/markdown")
async def export_report_markdown(report_id: int, db: AsyncSession = Depends(get_db)):
    """Export report as Markdown file"""
    report = await get_alive_by_id(db, Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    if not report.content_md:
        raise HTTPException(status_code=400, detail="Report content not available")

    # Generate filename
    from datetime import datetime
    timestamp = now().strftime("%Y%m%d_%H%M%S")
    filename = f"inspection_report_{report_id}_{timestamp}.md"

    return Response(
        content=report.content_md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/reports/export/{report_id}/pdf")
async def export_report_pdf(report_id: int, db: AsyncSession = Depends(get_db)):
    """Export report as PDF file"""
    report = await get_alive_by_id(db, Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    if not report.content_md:
        raise HTTPException(status_code=400, detail="Report content not available")

    try:
        from backend.utils.pdf_generator import markdown_to_pdf

        # Generate PDF from markdown
        pdf_bytes = markdown_to_pdf(report.content_md, report.title)

        # Generate filename
        from datetime import datetime
        timestamp = now().strftime("%Y%m%d_%H%M%S")
        filename = f"inspection_report_{report_id}_{timestamp}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF export not available. Please install: pip install reportlab. Error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.delete("/reports/{report_id}")
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an inspection report and clean up related triggers"""
    report = await get_alive_by_id(db, Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    # Clean up related inspection triggers (set report_id to NULL)
    from sqlalchemy import update
    await db.execute(
        update(InspectionTrigger)
        .where(InspectionTrigger.report_id == report_id)
        .values(report_id=None)
    )

    report.soft_delete(None)
    await db.commit()

    return {"message": "报告已删除", "report_id": report_id}


class BatchDeleteRequest(BaseModel):
    report_ids: List[int]


@router.post("/reports/batch-delete")
async def batch_delete_report(
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Batch delete inspection report"""
    if not request.report_ids:
        raise HTTPException(status_code=400, detail="报告ID列表不能为空")

    # Verify all report exist
    result = await db.execute(
        select(Report).where(Report.id.in_(request.report_ids), alive_filter(Report))
    )
    report = result.scalars().all()
    found_ids = {r.id for r in report}
    missing_ids = set(request.report_ids) - found_ids

    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"以下报告不存在: {', '.join(map(str, missing_ids))}"
        )

    # Clean up related inspection triggers
    from sqlalchemy import update
    await db.execute(
        update(InspectionTrigger)
        .where(InspectionTrigger.report_id.in_(request.report_ids))
        .values(report_id=None)
    )

    for report in report:
        report.soft_delete(None)

    await db.commit()

    return {
        "message": f"成功删除 {len(request.report_ids)} 个报告",
        "deleted_count": len(request.report_ids),
        "report_ids": request.report_ids
    }
