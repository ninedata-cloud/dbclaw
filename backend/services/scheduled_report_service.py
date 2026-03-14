"""
Scheduled Report Service

Core service for managing automated report generation based on datasource importance levels.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.models.scheduled_report_config import ScheduledReportConfig
from backend.models.scheduled_report_history import ScheduledReportHistory
from backend.models.report import Report
from backend.services.report_generator import generate_report
from backend.services.ai_report_generator import generate_ai_report

logger = logging.getLogger(__name__)


class ScheduledReportService:
    """Service for managing scheduled report generation"""

    # Schedule intervals by importance level (in seconds)
    INTERVAL_MAP = {
        "core": 3600,        # 1 hour
        "production": 14400,  # 4 hours
        "development": 86400, # 24 hours
        "test": 86400,        # 24 hours
        "temporary": None     # No scheduled reports
    }

    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler

    def _get_interval_from_importance(self, importance_level: str) -> Optional[int]:
        """Get schedule interval in seconds from importance level"""
        return self.INTERVAL_MAP.get(importance_level)

    def _format_interval_display(self, seconds: int) -> str:
        """Format interval in seconds to human-readable string"""
        if seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour" if hours == 1 else f"{hours} hours"
        else:
            days = seconds // 86400
            return f"{days} day" if days == 1 else f"{days} days"

    async def initialize_all_schedules(self):
        """Initialize schedules for all active datasources on startup"""
        logger.info("Initializing scheduled report service...")

        async for db in get_db():
            try:
                # Get all datasources with importance != temporary
                result = await db.execute(
                    select(Datasource).where(
                        and_(
                            Datasource.importance_level != "temporary",
                            Datasource.importance_level.isnot(None)
                        )
                    )
                )
                datasources = result.scalars().all()

                logger.info(f"Found {len(datasources)} datasources eligible for scheduled reports")

                for datasource in datasources:
                    await self._ensure_config_exists(db, datasource)

                await db.commit()

                # Add scheduler jobs for all enabled configs
                result = await db.execute(
                    select(ScheduledReportConfig).where(ScheduledReportConfig.enabled == True)
                )
                configs = result.scalars().all()

                for config in configs:
                    self._add_scheduler_job(config)

                logger.info(f"Initialized {len(configs)} scheduled report jobs")

            except Exception as e:
                logger.error(f"Error initializing schedules: {e}", exc_info=True)
                await db.rollback()
            finally:
                break

    async def _ensure_config_exists(self, db: AsyncSession, datasource: Datasource):
        """Ensure a config exists for the datasource, create if not"""
        result = await db.execute(
            select(ScheduledReportConfig).where(
                ScheduledReportConfig.datasource_id == datasource.id
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            interval = self._get_interval_from_importance(datasource.importance_level)
            if interval:
                config = ScheduledReportConfig(
                    datasource_id=datasource.id,
                    enabled=True,
                    schedule_interval=interval,
                    next_scheduled_at=datetime.utcnow() + timedelta(seconds=interval)
                )
                db.add(config)
                logger.info(f"Created schedule config for datasource {datasource.id} ({datasource.name})")

    def _add_scheduler_job(self, config: ScheduledReportConfig):
        """Add APScheduler job for a config"""
        job_id = f"scheduled_report_{config.id}"

        # Remove existing job if present
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        # Add new job with interval trigger
        self.scheduler.add_job(
            self.generate_scheduled_report,
            trigger=IntervalTrigger(seconds=config.schedule_interval),
            id=job_id,
            args=[config.id],
            replace_existing=True,
            next_run_time=config.next_scheduled_at or datetime.utcnow()
        )
        logger.info(f"Added scheduler job {job_id} with interval {config.schedule_interval}s")

    async def add_schedule_for_datasource(self, datasource_id: int) -> Optional[ScheduledReportConfig]:
        """Add schedule for a new datasource"""
        async for db in get_db():
            try:
                # Get datasource
                result = await db.execute(
                    select(Datasource).where(Datasource.id == datasource_id)
                )
                datasource = result.scalar_one_or_none()

                if not datasource:
                    logger.error(f"Datasource {datasource_id} not found")
                    return None

                # Check if temporary
                if datasource.importance_level == "temporary":
                    logger.info(f"Datasource {datasource_id} is temporary, skipping schedule")
                    return None

                # Check if config already exists
                result = await db.execute(
                    select(ScheduledReportConfig).where(
                        ScheduledReportConfig.datasource_id == datasource_id
                    )
                )
                existing_config = result.scalar_one_or_none()

                if existing_config:
                    logger.info(f"Schedule already exists for datasource {datasource_id}")
                    return existing_config

                # Create new config
                interval = self._get_interval_from_importance(datasource.importance_level)
                if not interval:
                    logger.warning(f"No interval defined for importance level {datasource.importance_level}")
                    return None

                config = ScheduledReportConfig(
                    datasource_id=datasource_id,
                    enabled=True,
                    schedule_interval=interval,
                    next_scheduled_at=datetime.utcnow() + timedelta(seconds=interval)
                )
                db.add(config)
                await db.commit()
                await db.refresh(config)

                # Add scheduler job
                self._add_scheduler_job(config)

                logger.info(f"Created schedule for datasource {datasource_id}")
                return config

            except Exception as e:
                logger.error(f"Error adding schedule for datasource {datasource_id}: {e}", exc_info=True)
                await db.rollback()
                return None
            finally:
                break

    async def update_schedule(self, datasource_id: int):
        """Update schedule when datasource importance changes"""
        async for db in get_db():
            try:
                # Get datasource and config
                result = await db.execute(
                    select(Datasource).where(Datasource.id == datasource_id)
                )
                datasource = result.scalar_one_or_none()

                if not datasource:
                    return

                result = await db.execute(
                    select(ScheduledReportConfig).where(
                        ScheduledReportConfig.datasource_id == datasource_id
                    )
                )
                config = result.scalar_one_or_none()

                # If temporary, remove schedule
                if datasource.importance_level == "temporary":
                    if config:
                        await self.remove_schedule(datasource_id)
                    return

                # Get new interval
                new_interval = self._get_interval_from_importance(datasource.importance_level)
                if not new_interval:
                    return

                if config:
                    # Update existing config
                    config.schedule_interval = new_interval
                    config.next_scheduled_at = datetime.utcnow() + timedelta(seconds=new_interval)
                    await db.commit()

                    # Update scheduler job
                    if config.enabled:
                        self._add_scheduler_job(config)

                    logger.info(f"Updated schedule for datasource {datasource_id}")
                else:
                    # Create new config
                    await self.add_schedule_for_datasource(datasource_id)

            except Exception as e:
                logger.error(f"Error updating schedule for datasource {datasource_id}: {e}", exc_info=True)
                await db.rollback()
            finally:
                break

    async def remove_schedule(self, datasource_id: int):
        """Remove schedule for a datasource"""
        async for db in get_db():
            try:
                result = await db.execute(
                    select(ScheduledReportConfig).where(
                        ScheduledReportConfig.datasource_id == datasource_id
                    )
                )
                config = result.scalar_one_or_none()

                if config:
                    # Remove scheduler job
                    job_id = f"scheduled_report_{config.id}"
                    if self.scheduler.get_job(job_id):
                        self.scheduler.remove_job(job_id)

                    # Delete config (cascade will delete history)
                    await db.delete(config)
                    await db.commit()

                    logger.info(f"Removed schedule for datasource {datasource_id}")

            except Exception as e:
                logger.error(f"Error removing schedule for datasource {datasource_id}: {e}", exc_info=True)
                await db.rollback()
            finally:
                break

    async def generate_scheduled_report(self, config_id: int):
        """Generate a scheduled report (called by APScheduler)"""
        start_time = datetime.utcnow()
        scheduled_time = start_time

        async for db in get_db():
            try:
                # Get config
                result = await db.execute(
                    select(ScheduledReportConfig).where(ScheduledReportConfig.id == config_id)
                )
                config = result.scalar_one_or_none()

                if not config or not config.enabled:
                    logger.info(f"Config {config_id} not found or disabled, skipping")
                    return

                # Check for recent manual reports (deduplication)
                cutoff_time = datetime.utcnow() - timedelta(minutes=30)
                result = await db.execute(
                    select(Report).where(
                        and_(
                            Report.datasource_id == config.datasource_id,
                            Report.is_scheduled == False,
                            Report.created_at >= cutoff_time,
                            Report.status == "completed"
                        )
                    )
                    .order_by(Report.created_at.desc())
                    .limit(1)
                )
                recent_manual_report = result.scalar_one_or_none()

                if recent_manual_report:
                    # Skip generation, record in history
                    history = ScheduledReportHistory(
                        config_id=config_id,
                        datasource_id=config.datasource_id,
                        scheduled_time=scheduled_time,
                        status="skipped",
                        skip_reason=f"Manual report generated at {recent_manual_report.created_at}"
                    )
                    db.add(history)

                    # Update next scheduled time
                    config.next_scheduled_at = datetime.utcnow() + timedelta(seconds=config.schedule_interval)
                    await db.commit()

                    logger.info(f"Skipped scheduled report for datasource {config.datasource_id} (recent manual report exists)")
                    return

                # Generate report
                logger.info(f"Generating scheduled report for datasource {config.datasource_id}")

                # Get datasource for title
                datasource_result = await db.execute(
                    select(Datasource).where(Datasource.id == config.datasource_id)
                )
                datasource = datasource_result.scalar_one()

                # Create report record
                report = Report(
                    datasource_id=config.datasource_id,
                    title=f"Scheduled Report - {datasource.name}",
                    report_type=config.report_type,
                    status="generating",
                    generation_method="ai" if config.use_ai_analysis else "rule-based",
                    ai_model_id=config.ai_model_id if config.use_ai_analysis else None,
                    kb_ids=eval(config.kb_ids) if config.kb_ids else None,
                    is_scheduled=True,
                    schedule_config_id=config_id,
                    retention_days=30
                )
                db.add(report)
                await db.commit()
                await db.refresh(report)

                # Generate report content
                if config.use_ai_analysis and config.ai_model_id:
                    # AI-powered report - consume the generator
                    async for event in generate_ai_report(
                        report_id=report.id,
                        datasource_id=config.datasource_id,
                        report_type=config.report_type,
                        model_id=config.ai_model_id,
                        kb_ids=eval(config.kb_ids) if config.kb_ids else [],
                        db=db
                    ):
                        # Just consume events, don't need to process them
                        if event.get("type") == "error":
                            raise Exception(event.get("message", "AI report generation failed"))
                else:
                    # Rule-based report - wait for completion
                    await generate_report(report.id, config.datasource_id, config.report_type)

                # Refresh report to get updated status and content from generate_report
                db.expire(report)
                await db.refresh(report)

                # Verify report was actually completed
                if report.status != "completed":
                    raise Exception(f"Report generation did not complete successfully. Status: {report.status}")

                end_time = datetime.utcnow()
                duration = (end_time - start_time).total_seconds()

                # Record success in history
                history = ScheduledReportHistory(
                    config_id=config_id,
                    report_id=report.id,
                    datasource_id=config.datasource_id,
                    scheduled_time=scheduled_time,
                    actual_generation_time=start_time,
                    generation_duration_seconds=duration,
                    status="completed"
                )
                db.add(history)

                # Update config
                config.last_generated_at = end_time
                config.next_scheduled_at = datetime.utcnow() + timedelta(seconds=config.schedule_interval)

                await db.commit()

                logger.info(f"Successfully generated scheduled report {report.id} for datasource {config.datasource_id} in {duration:.2f}s")

            except Exception as e:
                logger.error(f"Error generating scheduled report for config {config_id}: {e}", exc_info=True)

                # Record failure in history
                try:
                    if config:
                        end_time = datetime.utcnow()
                        duration = (end_time - start_time).total_seconds()

                        history = ScheduledReportHistory(
                            config_id=config_id,
                            datasource_id=config.datasource_id,
                            scheduled_time=scheduled_time,
                            actual_generation_time=start_time,
                            generation_duration_seconds=duration,
                            status="failed",
                            error_message=str(e)
                        )
                        db.add(history)

                        # Update next scheduled time (don't disable on failure)
                        config.next_scheduled_at = datetime.utcnow() + timedelta(seconds=config.schedule_interval)

                        await db.commit()
                except Exception as inner_e:
                    logger.error(f"Error recording failure: {inner_e}", exc_info=True)
                    await db.rollback()
            finally:
                break

    async def cleanup_old_reports(self):
        """Delete old scheduled reports based on retention policy"""
        logger.info("Starting scheduled report cleanup...")

        async for db in get_db():
            try:
                # Find reports to delete
                result = await db.execute(
                    select(Report).where(
                        and_(
                            Report.is_scheduled == True,
                            Report.retention_days.isnot(None)
                        )
                    )
                )
                reports = result.scalars().all()

                deleted_count = 0
                for report in reports:
                    age_days = (datetime.utcnow() - report.created_at).days
                    if age_days > report.retention_days:
                        await db.delete(report)
                        deleted_count += 1

                await db.commit()
                logger.info(f"Cleanup completed: deleted {deleted_count} old scheduled reports")

            except Exception as e:
                logger.error(f"Error during cleanup: {e}", exc_info=True)
                await db.rollback()
            finally:
                break
