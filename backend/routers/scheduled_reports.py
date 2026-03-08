"""
Scheduled Reports API Router

Endpoints for managing scheduled report generation and viewing history.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.models.scheduled_report_config import ScheduledReportConfig
from backend.models.scheduled_report_history import ScheduledReportHistory
from backend.models.report import Report
from backend.models.ai_model import AIModel
from backend.schemas.scheduled_report import (
    ScheduledReportConfigCreate,
    ScheduledReportConfigUpdate,
    ScheduledReportConfigResponse,
    ScheduledReportHistoryResponse,
    ScheduledReportStatsResponse,
    DatasourceScheduledReportStatsResponse
)
from backend.routers.auth import get_current_user
from backend.services.scheduled_report_service import ScheduledReportService
from backend.services import metric_collector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduled-reports", tags=["scheduled-reports"])

# Global service instance (lazy initialized)
_scheduled_report_service = None


def get_scheduled_report_service() -> ScheduledReportService:
    """Get or create the scheduled report service instance"""
    global _scheduled_report_service
    if _scheduled_report_service is None:
        if metric_collector.scheduler is None:
            raise RuntimeError("Scheduler not initialized. App may not have started properly.")
        _scheduled_report_service = ScheduledReportService(metric_collector.scheduler)
    return _scheduled_report_service

# Rate limiting cache for manual triggers
_trigger_cache = {}


def _format_interval_display(seconds: int) -> str:
    """Format interval in seconds to human-readable string"""
    if seconds < 3600:
        return f"{seconds // 60} minutes"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    else:
        days = seconds // 86400
        return f"{days} day" if days == 1 else f"{days} days"


@router.post("/configs", response_model=ScheduledReportConfigResponse)
async def create_schedule_config(
    config_data: ScheduledReportConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create or enable scheduled report configuration for a datasource"""
    try:
        # Get datasource
        result = await db.execute(
            select(Datasource).where(Datasource.id == config_data.datasource_id)
        )
        datasource = result.scalar_one_or_none()

        if not datasource:
            raise HTTPException(status_code=404, detail="Datasource not found")

        # Check if temporary
        if datasource.importance_level == "temporary":
            raise HTTPException(
                status_code=400,
                detail="Cannot create scheduled reports for temporary datasources"
            )

        # Check if config already exists
        result = await db.execute(
            select(ScheduledReportConfig).where(
                ScheduledReportConfig.datasource_id == config_data.datasource_id
            )
        )
        existing_config = result.scalar_one_or_none()

        if existing_config:
            raise HTTPException(
                status_code=400,
                detail="Schedule configuration already exists for this datasource"
            )

        # Calculate interval from importance
        interval = get_scheduled_report_service()._get_interval_from_importance(datasource.importance_level)
        if not interval:
            raise HTTPException(
                status_code=400,
                detail=f"No schedule interval defined for importance level {datasource.importance_level}"
            )

        # Create config
        config = ScheduledReportConfig(
            datasource_id=config_data.datasource_id,
            enabled=config_data.enabled,
            report_type=config_data.report_type,
            schedule_interval=interval,
            use_ai_analysis=config_data.use_ai_analysis,
            ai_model_id=config_data.ai_model_id,
            kb_ids=str(config_data.kb_ids) if config_data.kb_ids else None,
            next_scheduled_at=datetime.utcnow() + timedelta(seconds=interval)
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        # Add scheduler job if enabled
        if config.enabled:
            get_scheduled_report_service()._add_scheduler_job(config)

        # Build response
        response = ScheduledReportConfigResponse(
            id=config.id,
            datasource_id=config.datasource_id,
            datasource_name=datasource.name,
            datasource_type=datasource.db_type,
            importance_level=datasource.importance_level,
            enabled=config.enabled,
            report_type=config.report_type,
            schedule_interval=config.schedule_interval,
            schedule_interval_display=_format_interval_display(config.schedule_interval),
            use_ai_analysis=config.use_ai_analysis,
            ai_model_id=config.ai_model_id,
            kb_ids=eval(config.kb_ids) if config.kb_ids else None,
            last_generated_at=config.last_generated_at,
            next_scheduled_at=config.next_scheduled_at,
            created_at=config.created_at,
            updated_at=config.updated_at
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating schedule config: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs", response_model=List[ScheduledReportConfigResponse])
async def list_schedule_configs(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all scheduled report configurations"""
    try:
        result = await db.execute(
            select(ScheduledReportConfig, Datasource, AIModel)
            .join(Datasource, ScheduledReportConfig.datasource_id == Datasource.id)
            .outerjoin(AIModel, ScheduledReportConfig.ai_model_id == AIModel.id)
            .order_by(ScheduledReportConfig.created_at.desc())
        )
        rows = result.all()

        configs = []
        for config, datasource, ai_model in rows:
            configs.append(ScheduledReportConfigResponse(
                id=config.id,
                datasource_id=config.datasource_id,
                datasource_name=datasource.name,
                datasource_type=datasource.db_type,
                importance_level=datasource.importance_level,
                enabled=config.enabled,
                report_type=config.report_type,
                schedule_interval=config.schedule_interval,
                schedule_interval_display=_format_interval_display(config.schedule_interval),
                use_ai_analysis=config.use_ai_analysis,
                ai_model_id=config.ai_model_id,
                ai_model_name=ai_model.name if ai_model else None,
                kb_ids=eval(config.kb_ids) if config.kb_ids else None,
                last_generated_at=config.last_generated_at,
                next_scheduled_at=config.next_scheduled_at,
                created_at=config.created_at,
                updated_at=config.updated_at
            ))

        return configs

    except Exception as e:
        logger.error(f"Error listing schedule configs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{datasource_id}", response_model=ScheduledReportConfigResponse)
async def get_schedule_config(
    datasource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get schedule configuration for a specific datasource"""
    try:
        result = await db.execute(
            select(ScheduledReportConfig, Datasource, AIModel)
            .join(Datasource, ScheduledReportConfig.datasource_id == Datasource.id)
            .outerjoin(AIModel, ScheduledReportConfig.ai_model_id == AIModel.id)
            .where(ScheduledReportConfig.datasource_id == datasource_id)
        )
        row = result.first()

        if not row:
            raise HTTPException(status_code=404, detail="Schedule configuration not found")

        config, datasource, ai_model = row

        return ScheduledReportConfigResponse(
            id=config.id,
            datasource_id=config.datasource_id,
            datasource_name=datasource.name,
            datasource_type=datasource.db_type,
            importance_level=datasource.importance_level,
            enabled=config.enabled,
            report_type=config.report_type,
            schedule_interval=config.schedule_interval,
            schedule_interval_display=_format_interval_display(config.schedule_interval),
            use_ai_analysis=config.use_ai_analysis,
            ai_model_id=config.ai_model_id,
            ai_model_name=ai_model.name if ai_model else None,
            kb_ids=eval(config.kb_ids) if config.kb_ids else None,
            last_generated_at=config.last_generated_at,
            next_scheduled_at=config.next_scheduled_at,
            created_at=config.created_at,
            updated_at=config.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/configs/{config_id}", response_model=ScheduledReportConfigResponse)
async def update_schedule_config(
    config_id: int,
    config_data: ScheduledReportConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update schedule configuration"""
    try:
        result = await db.execute(
            select(ScheduledReportConfig).where(ScheduledReportConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="Schedule configuration not found")

        # Update fields
        if config_data.enabled is not None:
            config.enabled = config_data.enabled
        if config_data.report_type is not None:
            config.report_type = config_data.report_type
        if config_data.use_ai_analysis is not None:
            config.use_ai_analysis = config_data.use_ai_analysis
        if config_data.ai_model_id is not None:
            config.ai_model_id = config_data.ai_model_id
        if config_data.kb_ids is not None:
            config.kb_ids = str(config_data.kb_ids)
        if config_data.retention_days is not None:
            # Update retention for future reports
            pass

        await db.commit()
        await db.refresh(config)

        # Update scheduler job
        if config.enabled:
            get_scheduled_report_service()._add_scheduler_job(config)
        else:
            job_id = f"scheduled_report_{config.id}"
            if metric_collector.scheduler and metric_collector.scheduler.get_job(job_id):
                metric_collector.scheduler.remove_job(job_id)

        # Get datasource for response
        result = await db.execute(
            select(Datasource).where(Datasource.id == config.datasource_id)
        )
        datasource = result.scalar_one()

        return ScheduledReportConfigResponse(
            id=config.id,
            datasource_id=config.datasource_id,
            datasource_name=datasource.name,
            datasource_type=datasource.db_type,
            importance_level=datasource.importance_level,
            enabled=config.enabled,
            report_type=config.report_type,
            schedule_interval=config.schedule_interval,
            schedule_interval_display=_format_interval_display(config.schedule_interval),
            use_ai_analysis=config.use_ai_analysis,
            ai_model_id=config.ai_model_id,
            kb_ids=eval(config.kb_ids) if config.kb_ids else None,
            last_generated_at=config.last_generated_at,
            next_scheduled_at=config.next_scheduled_at,
            created_at=config.created_at,
            updated_at=config.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schedule config: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/configs/{config_id}")
async def delete_schedule_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete schedule configuration"""
    try:
        result = await db.execute(
            select(ScheduledReportConfig).where(ScheduledReportConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="Schedule configuration not found")

        # Remove scheduler job
        job_id = f"scheduled_report_{config.id}"
        if metric_collector.scheduler and metric_collector.scheduler.get_job(job_id):
            metric_collector.scheduler.remove_job(job_id)

        # Delete config
        await db.delete(config)
        await db.commit()

        return {"message": "Schedule configuration deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting schedule config: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{config_id}/enable")
async def enable_schedule(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Enable a disabled schedule"""
    try:
        result = await db.execute(
            select(ScheduledReportConfig).where(ScheduledReportConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="Schedule configuration not found")

        config.enabled = True
        config.next_scheduled_at = datetime.utcnow() + timedelta(seconds=config.schedule_interval)
        await db.commit()

        # Add scheduler job
        get_scheduled_report_service()._add_scheduler_job(config)

        return {"message": "Schedule enabled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling schedule: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{config_id}/disable")
async def disable_schedule(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Disable a schedule"""
    try:
        result = await db.execute(
            select(ScheduledReportConfig).where(ScheduledReportConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="Schedule configuration not found")

        config.enabled = False
        await db.commit()

        # Remove scheduler job
        job_id = f"scheduled_report_{config.id}"
        if metric_collector.scheduler and metric_collector.scheduler.get_job(job_id):
            metric_collector.scheduler.remove_job(job_id)

        return {"message": "Schedule disabled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling schedule: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[ScheduledReportHistoryResponse])
async def list_history(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    datasource_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List scheduled report generation history with pagination"""
    try:
        # Build query
        query = select(ScheduledReportHistory, Datasource).join(
            Datasource, ScheduledReportHistory.datasource_id == Datasource.id
        )

        # Apply filters
        if datasource_id:
            query = query.where(ScheduledReportHistory.datasource_id == datasource_id)
        if status:
            query = query.where(ScheduledReportHistory.status == status)

        # Order and paginate
        query = query.order_by(desc(ScheduledReportHistory.created_at))
        query = query.offset((page - 1) * limit).limit(limit)

        result = await db.execute(query)
        rows = result.all()

        history_list = []
        for history, datasource in rows:
            history_list.append(ScheduledReportHistoryResponse(
                id=history.id,
                config_id=history.config_id,
                report_id=history.report_id,
                datasource_id=history.datasource_id,
                datasource_name=datasource.name,
                scheduled_time=history.scheduled_time,
                actual_generation_time=history.actual_generation_time,
                generation_duration_seconds=history.generation_duration_seconds,
                status=history.status,
                skip_reason=history.skip_reason,
                error_message=history.error_message,
                created_at=history.created_at
            ))

        return history_list

    except Exception as e:
        logger.error(f"Error listing history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{datasource_id}", response_model=List[ScheduledReportHistoryResponse])
async def get_datasource_history(
    datasource_id: int,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get history for a specific datasource"""
    return await list_history(
        page=1,
        limit=limit,
        datasource_id=datasource_id,
        db=db,
        current_user=current_user
    )


@router.post("/trigger/{datasource_id}")
async def trigger_manual_generation(
    datasource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Manually trigger scheduled report generation (rate limited)"""
    try:
        # Rate limiting check
        cache_key = f"trigger_{datasource_id}"
        last_trigger = _trigger_cache.get(cache_key)

        if last_trigger:
            elapsed = (datetime.utcnow() - last_trigger).total_seconds()
            if elapsed < 300:  # 5 minutes
                remaining = int(300 - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Please wait {remaining} seconds before triggering again."
                )

        # Get config
        result = await db.execute(
            select(ScheduledReportConfig).where(
                ScheduledReportConfig.datasource_id == datasource_id
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="Schedule configuration not found")

        # Update rate limit cache
        _trigger_cache[cache_key] = datetime.utcnow()

        # Trigger generation
        await get_scheduled_report_service().generate_scheduled_report(config.id)

        return {"message": "Report generation triggered successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering manual generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=ScheduledReportStatsResponse)
async def get_overall_stats(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get overall scheduled report statistics"""
    try:
        # Total configs
        result = await db.execute(select(func.count(ScheduledReportConfig.id)))
        total_configs = result.scalar() or 0

        # Enabled configs
        result = await db.execute(
            select(func.count(ScheduledReportConfig.id)).where(ScheduledReportConfig.enabled == True)
        )
        enabled_configs = result.scalar() or 0

        # Total reports generated
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                ScheduledReportHistory.status == "completed"
            )
        )
        total_reports = result.scalar() or 0

        # Reports today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                and_(
                    ScheduledReportHistory.status == "completed",
                    ScheduledReportHistory.created_at >= today_start
                )
            )
        )
        reports_today = result.scalar() or 0

        # Reports this week
        week_start = today_start - timedelta(days=today_start.weekday())
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                and_(
                    ScheduledReportHistory.status == "completed",
                    ScheduledReportHistory.created_at >= week_start
                )
            )
        )
        reports_this_week = result.scalar() or 0

        # Reports this month
        month_start = today_start.replace(day=1)
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                and_(
                    ScheduledReportHistory.status == "completed",
                    ScheduledReportHistory.created_at >= month_start
                )
            )
        )
        reports_this_month = result.scalar() or 0

        # Failed and skipped counts
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                ScheduledReportHistory.status == "failed"
            )
        )
        failed_count = result.scalar() or 0

        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                ScheduledReportHistory.status == "skipped"
            )
        )
        skipped_count = result.scalar() or 0

        # Success rate
        total_attempts = total_reports + failed_count
        success_rate = (total_reports / total_attempts * 100) if total_attempts > 0 else 0.0

        # Average duration
        result = await db.execute(
            select(func.avg(ScheduledReportHistory.generation_duration_seconds)).where(
                ScheduledReportHistory.status == "completed"
            )
        )
        avg_duration = result.scalar()

        return ScheduledReportStatsResponse(
            total_configs=total_configs,
            enabled_configs=enabled_configs,
            total_reports_generated=total_reports,
            reports_today=reports_today,
            reports_this_week=reports_this_week,
            reports_this_month=reports_this_month,
            success_rate=round(success_rate, 2),
            average_duration_seconds=round(avg_duration, 2) if avg_duration else None,
            failed_count=failed_count,
            skipped_count=skipped_count
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{datasource_id}", response_model=DatasourceScheduledReportStatsResponse)
async def get_datasource_stats(
    datasource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get statistics for a specific datasource"""
    try:
        # Get datasource
        result = await db.execute(
            select(Datasource).where(Datasource.id == datasource_id)
        )
        datasource = result.scalar_one_or_none()

        if not datasource:
            raise HTTPException(status_code=404, detail="Datasource not found")

        # Get config
        result = await db.execute(
            select(ScheduledReportConfig).where(
                ScheduledReportConfig.datasource_id == datasource_id
            )
        )
        config = result.scalar_one_or_none()

        # Total reports
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                ScheduledReportHistory.datasource_id == datasource_id
            )
        )
        total_reports = result.scalar() or 0

        # Successful reports
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                and_(
                    ScheduledReportHistory.datasource_id == datasource_id,
                    ScheduledReportHistory.status == "completed"
                )
            )
        )
        successful_reports = result.scalar() or 0

        # Failed reports
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                and_(
                    ScheduledReportHistory.datasource_id == datasource_id,
                    ScheduledReportHistory.status == "failed"
                )
            )
        )
        failed_reports = result.scalar() or 0

        # Skipped reports
        result = await db.execute(
            select(func.count(ScheduledReportHistory.id)).where(
                and_(
                    ScheduledReportHistory.datasource_id == datasource_id,
                    ScheduledReportHistory.status == "skipped"
                )
            )
        )
        skipped_reports = result.scalar() or 0

        # Success rate
        success_rate = (successful_reports / total_reports * 100) if total_reports > 0 else 0.0

        # Average duration
        result = await db.execute(
            select(func.avg(ScheduledReportHistory.generation_duration_seconds)).where(
                and_(
                    ScheduledReportHistory.datasource_id == datasource_id,
                    ScheduledReportHistory.status == "completed"
                )
            )
        )
        avg_duration = result.scalar()

        return DatasourceScheduledReportStatsResponse(
            datasource_id=datasource_id,
            datasource_name=datasource.name,
            total_reports=total_reports,
            successful_reports=successful_reports,
            failed_reports=failed_reports,
            skipped_reports=skipped_reports,
            success_rate=round(success_rate, 2),
            average_duration_seconds=round(avg_duration, 2) if avg_duration else None,
            last_generated_at=config.last_generated_at if config else None,
            next_scheduled_at=config.next_scheduled_at if config else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting datasource stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports", response_model=List[dict])
async def list_scheduled_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    datasource_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List only scheduled reports"""
    try:
        query = select(Report).where(Report.is_scheduled == True)

        if datasource_id:
            query = query.where(Report.datasource_id == datasource_id)

        query = query.order_by(desc(Report.created_at))
        query = query.offset((page - 1) * limit).limit(limit)

        result = await db.execute(query)
        reports = result.scalars().all()

        return [
            {
                "id": report.id,
                "datasource_id": report.datasource_id,
                "title": report.title,
                "report_type": report.report_type,
                "status": report.status,
                "created_at": report.created_at,
                "completed_at": report.completed_at,
                "generation_method": report.generation_method
            }
            for report in reports
        ]

    except Exception as e:
        logger.error(f"Error listing scheduled reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
