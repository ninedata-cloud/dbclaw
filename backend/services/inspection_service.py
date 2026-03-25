"""Database Intelligent Inspection Service - unified threshold-based monitoring and reporting"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.inspection_config import InspectionConfig
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.datasource import Datasource
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.report import Report
from backend.utils.datetime_helper import now as get_now

logger = logging.getLogger(__name__)


class InspectionService:
    """Unified service for scheduled database inspections and reporting"""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.running = False

    async def start(self):
        """Start background tasks for scheduled inspections"""
        self.running = True
        logger.info("InspectionService started")

        # Initialize configs for all datasources
        async with self.db_session_factory() as db:
            await self.initialize_all_configs(db)

        # Start scheduler loop
        asyncio.create_task(self._scheduler_loop())

    async def stop(self):
        """Stop background tasks"""
        self.running = False
        logger.info("InspectionService stopped")

    async def initialize_all_configs(self, db: AsyncSession):
        """Create default inspection configs for datasources that don't have one"""
        result = await db.execute(select(Datasource))
        datasources = result.scalars().all()

        for ds in datasources:
            existing = await db.execute(
                select(InspectionConfig).where(InspectionConfig.datasource_id == ds.id)
            )
            if not existing.scalar_one_or_none():
                config = InspectionConfig(
                    datasource_id=ds.id,
                    enabled=True,
                    schedule_interval=86400,  # daily
                    use_ai_analysis=True,
                    threshold_rules={
                        "cpu_usage": {"threshold": 50, "duration": 60},
                        "disk_usage": {"threshold": 80, "duration": 60},
                        "memory_usage": {"threshold": 95, "duration": 60},
                        "connections": {"threshold": 20, "duration": 60}
                    },
                    next_scheduled_at=get_now() + timedelta(seconds=86400)
                )
                db.add(config)

        await db.commit()
        logger.info(f"Initialized inspection configs for {len(datasources)} datasources")

    async def trigger_inspection(self, db: AsyncSession, datasource_id: int,
                                trigger_type: str, reason: str = None,
                                metric_snapshot: Dict[str, Any] = None,
                                alert_id: Optional[int] = None) -> int:
        """Manually or programmatically trigger an inspection"""
        trigger = InspectionTrigger(
            datasource_id=datasource_id,
            trigger_type=trigger_type,
            trigger_reason=reason,
            metric_snapshot=metric_snapshot,
            alert_id=alert_id,
            processed=False
        )
        db.add(trigger)
        await db.flush()
        await db.commit()

        logger.info(f"Created {trigger_type} trigger {trigger.id} for datasource {datasource_id}")

        # Generate report synchronously for manual triggers
        if trigger_type == "manual":
            await self._generate_report(db, trigger.id)
        else:
            asyncio.create_task(self._generate_report_async(trigger.id))

        return trigger.id

    async def _scheduler_loop(self):
        """Background loop to check for scheduled inspections"""
        while self.running:
            try:
                async with self.db_session_factory() as db:
                    now = get_now()
                    result = await db.execute(
                        select(InspectionConfig).where(
                            and_(
                                InspectionConfig.enabled == True,
                                InspectionConfig.next_scheduled_at <= now
                            )
                        )
                    )
                    configs = result.scalars().all()

                    for config in configs:
                        await self.trigger_inspection(db, config.datasource_id, "scheduled", "Scheduled inspection")
                        config.last_scheduled_at = now
                        config.next_scheduled_at = now + timedelta(seconds=config.schedule_interval)

                    await db.commit()

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            await asyncio.sleep(60)

    async def _generate_report_async(self, trigger_id: int):
        """Generate report in background task"""
        try:
            async with self.db_session_factory() as db:
                await self._generate_report(db, trigger_id)
        except Exception as e:
            logger.error(f"Error generating report for trigger {trigger_id}: {e}", exc_info=True)

    async def _generate_report(self, db: AsyncSession, trigger_id: int):
        """Generate comprehensive inspection report"""
        from backend.services.report_generator import ReportGenerator

        result = await db.execute(
            select(InspectionTrigger).where(InspectionTrigger.id == trigger_id)
        )
        trigger = result.scalar_one_or_none()
        if not trigger or trigger.processed:
            return

        generator = ReportGenerator(db)
        report_id = await generator.generate_inspection_report(trigger_id)

        trigger.processed = True
        trigger.report_id = report_id

        report = await db.get(Report, report_id)
        if report and trigger.alert_id:
            report.alert_id = trigger.alert_id

        await db.commit()

        logger.info(f"Generated report {report_id} for trigger {trigger_id}")
