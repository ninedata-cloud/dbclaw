"""API endpoints for database intelligent inspection"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import List, Optional
from pydantic import BaseModel
import logging

from backend.database import get_db
from backend.utils.security import escape_html
from backend.models.inspection_config import InspectionConfig
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.report import Report
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.services.inspection_service import InspectionService
from backend.services.public_share_service import PublicShareService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


from datetime import datetime


class InspectionConfigSchema(BaseModel):
    enabled: bool
    schedule_interval: int
    use_ai_analysis: bool
    ai_model_id: Optional[int] = None
    kb_ids: List[int] = []
    threshold_rules: dict


class InspectionConfigResponse(BaseModel):
    id: int
    datasource_id: int
    enabled: bool
    schedule_interval: int
    use_ai_analysis: bool
    ai_model_id: Optional[int] = None
    kb_ids: List[int] = []
    threshold_rules: dict
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


@router.get("/config/{datasource_id}", response_model=InspectionConfigResponse)
async def get_config(datasource_id: int, db: AsyncSession = Depends(get_db)):
    """Get inspection configuration for a datasource"""
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
            threshold_rules={}
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


@router.post("/config/{datasource_id}", response_model=InspectionConfigResponse)
async def create_or_update_config(
    datasource_id: int,
    config_data: InspectionConfigSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create or update inspection configuration"""
    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()

    from datetime import timedelta
    from backend.utils.datetime_helper import now as get_now
    if config:
        for key, value in config_data.dict().items():
            setattr(config, key, value)
        # Recalculate next_scheduled_at based on new interval
        config.next_scheduled_at = get_now() + timedelta(seconds=config_data.schedule_interval)
    else:
        config = InspectionConfig(datasource_id=datasource_id, **config_data.dict())
        config.next_scheduled_at = get_now() + timedelta(seconds=config_data.schedule_interval)
        db.add(config)

    await db.commit()
    await db.refresh(config)
    return config


@router.put("/config/{datasource_id}", response_model=InspectionConfigResponse)
async def update_config(
    datasource_id: int,
    config_data: InspectionConfigSchema,
    db: AsyncSession = Depends(get_db)
):
    """Update inspection configuration"""
    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    from datetime import timedelta
    from backend.utils.datetime_helper import now as get_now
    for key, value in config_data.dict().items():
        setattr(config, key, value)
    # Recalculate next_scheduled_at based on new interval
    config.next_scheduled_at = get_now() + timedelta(seconds=config_data.schedule_interval)

    await db.commit()
    await db.refresh(config)
    return config


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
        db, datasource_id, "manual", "Manual inspection"
    )

    result = await db.execute(
        select(InspectionTrigger).where(InspectionTrigger.id == trigger_id)
    )
    trigger = result.scalar_one()

    return TriggerResponse(trigger_id=trigger_id, report_id=trigger.report_id)


@router.get("/reports", response_model=dict)
async def list_all_reports(
    datasource_id: Optional[int] = None,
    trigger_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List all inspection reports with filters"""
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

    reports = [
        {
            "report_id": row.Report.id,
            "datasource_name": row.datasource_name,
            "title": row.Report.title,
            "trigger_type": row.Report.trigger_type,
            "trigger_reason": row.Report.trigger_reason,
            "created_at": row.Report.created_at.isoformat() if row.Report.created_at else "",
            "status": row.Report.status,
            "error_message": row.Report.error_message
        }
        for row in rows
    ]

    return {"reports": reports, "total": total}


@router.get("/reports/{datasource_id}", response_model=List[ReportListItem])
async def list_reports(
    datasource_id: int,
    trigger_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """List inspection reports for a datasource"""
    query = select(Report).where(Report.datasource_id == datasource_id, alive_filter(Report))

    if trigger_type:
        query = query.where(Report.trigger_type == trigger_type)

    query = query.order_by(Report.created_at.desc()).limit(limit)

    result = await db.execute(query)
    reports = result.scalars().all()

    return [
        ReportListItem(
            report_id=r.id,
            title=r.title,
            trigger_type=r.trigger_type,
            trigger_reason=r.trigger_reason,
            created_at=r.created_at.isoformat() if r.created_at else "",
            status=r.status,
            error_message=r.error_message
        )
        for r in reports
    ]


@router.get("/reports/detail/{report_id}")
async def get_report_detail(report_id: int, db: AsyncSession = Depends(get_db)):
    """Get full report details"""
    report = await get_alive_by_id(db, Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    return {
        "id": report.id,
        "title": report.title,
        "trigger_type": report.trigger_type,
        "trigger_reason": report.trigger_reason,
        "content_md": report.content_md,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "completed_at": report.completed_at.isoformat() if report.completed_at else None
    }


@router.get("/reports/public/{report_id}")
async def get_public_report_detail(
    report_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get report details with public share token"""
    PublicShareService.verify_report_share_token(token, report_id)
    report = await PublicShareService.get_report_or_404(db, report_id)
    return {
        "id": report.id,
        "title": report.title,
        "trigger_type": report.trigger_type,
        "trigger_reason": report.trigger_reason,
        "content_md": report.content_md,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "completed_at": report.completed_at.isoformat() if report.completed_at else None
    }


@router.get("/reports/public/{report_id}/page", response_class=HTMLResponse)
async def public_report_page(
    report_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Render public report detail page with datasource config and AI diagnosis"""
    PublicShareService.verify_report_share_token(token, report_id)
    report = await PublicShareService.get_report_or_404(db, report_id)

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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
async def batch_delete_reports(
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Batch delete inspection reports"""
    if not request.report_ids:
        raise HTTPException(status_code=400, detail="报告ID列表不能为空")

    # Verify all reports exist
    result = await db.execute(
        select(Report).where(Report.id.in_(request.report_ids), alive_filter(Report))
    )
    reports = result.scalars().all()
    found_ids = {r.id for r in reports}
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

    for report in reports:
        report.soft_delete(None)

    await db.commit()

    return {
        "message": f"成功删除 {len(request.report_ids)} 个报告",
        "deleted_count": len(request.report_ids),
        "report_ids": request.report_ids
    }
