"""API endpoints for database intelligent inspection"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import List, Optional
from pydantic import BaseModel

from backend.database import get_db
from backend.models.inspection_config import InspectionConfig
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.report import Report
from backend.services.inspection_service import InspectionService

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

    if config:
        for key, value in config_data.dict().items():
            setattr(config, key, value)
    else:
        config = InspectionConfig(datasource_id=datasource_id, **config_data.dict())
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

    for key, value in config_data.dict().items():
        setattr(config, key, value)

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
        Datasource, Report.datasource_id == Datasource.id, isouter=True
    )

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
    count_query = select(func.count()).select_from(Report)
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

    query = query.order_by(desc(Report.created_at)).limit(limit).offset(offset)
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
    query = select(Report).where(Report.datasource_id == datasource_id)

    if trigger_type:
        query = query.where(Report.trigger_type == trigger_type)

    query = query.order_by(desc(Report.created_at)).limit(limit)

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
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

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


@router.get("/reports/export/{report_id}/markdown")
async def export_report_markdown(report_id: int, db: AsyncSession = Depends(get_db)):
    """Export report as Markdown file"""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

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
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if not report.content_html:
        raise HTTPException(status_code=400, detail="Report HTML content not available")

    try:
        from weasyprint import HTML
        from io import BytesIO

        # Generate PDF from HTML
        pdf_buffer = BytesIO()
        HTML(string=report.content_html).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        # Generate filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"inspection_report_{report_id}_{timestamp}.pdf"

        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PDF export not available. Please install weasyprint: pip install weasyprint"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
