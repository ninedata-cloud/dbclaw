import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db
from backend.models.report import Report
from backend.models.connection import Connection
from backend.schemas.report import ReportGenerateRequest, ReportResponse
from backend.services.report_generator import generate_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", response_model=List[ReportResponse])
async def list_reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).order_by(desc(Report.created_at)))
    return result.scalars().all()


@router.post("/generate", response_model=ReportResponse)
async def generate_report_endpoint(req: ReportGenerateRequest, db: AsyncSession = Depends(get_db)):
    # Verify connection exists
    conn_result = await db.execute(select(Connection).where(Connection.id == req.connection_id))
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    title = req.title or f"Diagnostic Report - {conn.name}"
    report = Report(
        connection_id=req.connection_id,
        title=title,
        report_type=req.report_type,
        status="generating",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Run report generation in background
    asyncio.create_task(generate_report(report.id, req.connection_id, req.report_type))

    return report


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/download")
async def download_report(report_id: int, format: str = "md", db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "completed":
        raise HTTPException(status_code=400, detail="Report is not yet completed")

    if format == "pdf":
        try:
            from backend.utils.pdf_export import html_to_pdf
            if report.content_html:
                pdf_bytes = html_to_pdf(report.content_html)
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="report_{report_id}.pdf"'},
                )
            else:
                raise HTTPException(status_code=400, detail="No HTML content available for PDF generation")
        except (ImportError, RuntimeError, OSError) as e:
            # Fallback: serve the HTML report directly
            if report.content_html:
                return Response(
                    content=report.content_html,
                    media_type="text/html",
                    headers={"Content-Disposition": f'attachment; filename="report_{report_id}.html"'},
                )
            raise HTTPException(status_code=500, detail=f"PDF generation unavailable: {e}")
    else:
        content = report.content_md or "No content available"
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report_{report_id}.md"'},
        )
