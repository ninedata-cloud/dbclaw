import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db
from backend.models.report import Report
from backend.models.datasource import Datasource
from backend.schemas.report import ReportGenerateRequest, ReportResponse
from backend.services.report_generator import generate_report
from backend.services.ai_report_generator import generate_ai_report

from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[ReportResponse])
async def list_reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).order_by(desc(Report.created_at)))
    return result.scalars().all()


@router.post("/generate", response_model=ReportResponse)
async def generate_report_endpoint(req: ReportGenerateRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Verify datasource exists
    datasource_result = await db.execute(select(Datasource).where(Datasource.id == req.datasource_id))
    datasource = datasource_result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="Datasource not found")

    title = req.title or f"Diagnostic Report - {datasource.name}"
    report = Report(
        datasource_id=req.datasource_id,
        title=title,
        report_type=req.report_type,
        status="pending",  # Changed from "generating" to "pending"
        generation_method="ai" if req.ai_enabled else "rule-based",
        ai_model_id=req.model_id if req.ai_enabled else None,
        kb_ids=req.kb_ids if req.ai_enabled else None,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # If AI is disabled, run traditional report generation in background
    if not req.ai_enabled:
        asyncio.create_task(generate_report(report.id, req.datasource_id, req.report_type))

    # Otherwise, client will connect via WebSocket for streaming generation
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


@router.get("/{report_id}/view")
async def view_report(report_id: int, db: AsyncSession = Depends(get_db)):
    """View report HTML content online without download"""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "completed":
        raise HTTPException(status_code=400, detail="Report is not yet completed")

    content = report.content_html or "<html><body><h1>No content available</h1></body></html>"
    return Response(content=content, media_type="text/html")


@router.websocket("/ws/reports/generate/{report_id}")
async def generate_report_websocket(
    websocket: WebSocket,
    report_id: int,
    token: str = Query(default=None)
):
    """WebSocket endpoint for real-time AI report generation"""
    # Validate token for WebSocket connections
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    try:
        from backend.utils.security import decode_access_token
        payload = decode_access_token(token)
        if not payload.get("sub"):
            await websocket.close(code=1008, reason="Invalid token")
            return
        user_id = int(payload.get("sub"))
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    logger.info(f"Report generation WebSocket connected for report {report_id}, user {user_id}")

    try:
        from backend.database import async_session

        async with async_session() as db:
            # Get report and verify datasource access
            result = await db.execute(select(Report).where(Report.id == report_id))
            report = result.scalar_one_or_none()

            if not report:
                logger.error(f"Report {report_id} not found")
                await websocket.send_json({"type": "error", "message": "Report not found"})
                await websocket.close()
                return

            # Verify datasource exists and user has access
            datasource_result = await db.execute(select(Datasource).where(Datasource.id == report.datasource_id))
            datasource = datasource_result.scalar_one_or_none()

            if not datasource:
                logger.error(f"Datasource {report.datasource_id} not found for report {report_id}")
                await websocket.send_json({"type": "error", "message": "Datasource not found"})
                await websocket.close()
                return

            if report.status != "pending":
                logger.error(f"Report {report_id} status is {report.status}, expected 'pending'")
                await websocket.send_json({"type": "error", "message": f"Report is not in pending state (current: {report.status})"})
                await websocket.close()
                return

            # Update status to generating
            report.status = "generating"
            await db.commit()
            logger.info(f"Report {report_id} status updated to 'generating'")

            # Stream AI report generation with timeout
            try:
                async with asyncio.timeout(600):  # 10 minute timeout
                    async for event in generate_ai_report(
                        report_id=report_id,
                        datasource_id=report.datasource_id,
                        report_type=report.report_type,
                        model_id=report.ai_model_id,
                        kb_ids=report.kb_ids,
                        db=db,
                        user_id=user_id,
                        websocket=websocket
                    ):
                        await websocket.send_json(event)

                        if event["type"] == "done":
                            break
            except asyncio.TimeoutError:
                logger.error(f"Report generation timeout for report {report_id}")
                await websocket.send_json({"type": "error", "message": "Report generation timed out after 10 minutes"})
            except Exception as gen_error:
                logger.error(f"Error during report generation: {gen_error}", exc_info=True)
                await websocket.send_json({"type": "error", "message": f"Generation error: {str(gen_error)}"})

    except WebSocketDisconnect:
        logger.info(f"Report generation WebSocket disconnected for report {report_id}")
    except Exception as e:
        logger.error(f"Error in report generation WebSocket: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
