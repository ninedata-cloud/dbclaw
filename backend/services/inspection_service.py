"""Database Intelligent Inspection Service - unified threshold-based monitoring and reporting"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.inspection_config import InspectionConfig
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.datasource import Datasource
from backend.models.datasource_metric import DatasourceMetric
from backend.models.report import Report
from backend.models.soft_delete import alive_select, get_alive_by_id
from backend.utils.datetime_helper import now as get_now

logger = logging.getLogger(__name__)


def _extract_anomaly_metric_name(reason: Optional[str]) -> Optional[str]:
    if not reason:
        return None

    match = re.match(r"\s*([^=\s]+)\s*=", reason)
    if not match:
        return None
    return match.group(1).strip() or None


async def _get_trigger_dedup_window_minutes(db: AsyncSession) -> int:
    from backend.config import get_settings
    from backend.services.config_service import get_config

    dedup_minutes = await get_config(
        db,
        "inspection_dedup_window_minutes",
        default=get_settings().inspection_dedup_window_minutes,
    )
    if not dedup_minutes:
        return 0
    return int(dedup_minutes)


class InspectionService:
    """Unified service for scheduled database inspections and reporting"""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.running = False

    async def start(self):
        """Start background tasks for scheduled inspections"""
        self.running = True
        logger.info("InspectionService started")

        # Initialize configs for all datasource
        async with self.db_session_factory() as db:
            await self.initialize_all_configs(db)

        # Start scheduler loop
        asyncio.create_task(self._scheduler_loop())

    async def stop(self):
        """Stop background tasks"""
        self.running = False
        logger.info("InspectionService stopped")

    async def initialize_all_configs(self, db: AsyncSession):
        """Create default inspection configs for datasource that don't have one"""
        from backend.services.alert_template_service import (
            bind_default_template_to_all_inspection_config,
            ensure_default_alert_template,
            get_default_alert_template,
        )

        await ensure_default_alert_template(db)
        default_template = await get_default_alert_template(db)
        result = await db.execute(alive_select(Datasource))
        datasource = result.scalars().all()

        for ds in datasource:
            existing = await db.execute(
                select(InspectionConfig).where(InspectionConfig.datasource_id == ds.id)
            )
            if not existing.scalar_one_or_none():
                config = InspectionConfig(
                    datasource_id=ds.id,
                    is_enabled=True,
                    schedule_interval=86400,  # daily
                    use_ai_analysis=True,
                    alert_template_id=default_template.id if default_template else None,
                    threshold_rules={},
                    alert_engine_mode="inherit",
                    ai_policy_source="inline",
                    ai_shadow_enabled=False,
                    baseline_config={},
                    event_ai_config={},
                    next_scheduled_at=get_now() + timedelta(seconds=86400)
                )
                db.add(config)

        await bind_default_template_to_all_inspection_config(db)

        await db.commit()
        logger.info(f"Initialized inspection configs for {len(datasource)} datasource")

    async def trigger_inspection(self, db: AsyncSession, datasource_id: int,
                                trigger_type: str, reason: str = None,
                                datasource_metric: Dict[str, Any] = None,
                                alert_id: Optional[int] = None) -> int:
        """Manually or programmatically trigger an inspection"""
        recent_trigger = await self._find_recent_duplicate_trigger(
            db=db,
            datasource_id=datasource_id,
            trigger_type=trigger_type,
            reason=reason,
        )
        if recent_trigger:
            logger.info(
                "Skipping duplicate %s trigger for datasource %s, reusing trigger %s",
                trigger_type,
                datasource_id,
                recent_trigger.id,
            )
            return recent_trigger.id

        trigger = InspectionTrigger(
            datasource_id=datasource_id,
            trigger_type=trigger_type,
            trigger_reason=reason,
            datasource_metric=datasource_metric,
            alert_id=alert_id,
            is_processed=False
        )
        db.add(trigger)
        await db.flush()
        await db.commit()

        logger.info(f"Created {trigger_type} trigger {trigger.id} for datasource {datasource_id}")

        # Always generate the report asynchronously so the caller only creates a task.
        asyncio.create_task(self._generate_report_async(trigger.id))

        return trigger.id

    async def _find_recent_duplicate_trigger(
        self,
        db: AsyncSession,
        datasource_id: int,
        trigger_type: str,
        reason: Optional[str],
    ) -> Optional[InspectionTrigger]:
        if trigger_type not in {"anomaly", "connection_failure"}:
            return None

        dedup_minutes = await _get_trigger_dedup_window_minutes(db)
        if dedup_minutes <= 0:
            return None

        filters = [
            InspectionTrigger.datasource_id == datasource_id,
            InspectionTrigger.trigger_type == trigger_type,
            InspectionTrigger.triggered_at >= get_now() - timedelta(minutes=dedup_minutes),
        ]

        if trigger_type == "anomaly":
            metric_name = _extract_anomaly_metric_name(reason)
            if metric_name:
                filters.append(InspectionTrigger.trigger_reason.like(f"{metric_name}=%"))
            elif reason:
                filters.append(InspectionTrigger.trigger_reason == reason)

        result = await db.execute(
            select(InspectionTrigger)
            .where(and_(*filters))
            .order_by(desc(InspectionTrigger.triggered_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _scheduler_loop(self):
        """Background loop to check for scheduled inspections"""
        while self.running:
            try:
                async with self.db_session_factory() as db:
                    now = get_now()
                    result = await db.execute(
                        select(InspectionConfig).where(
                            and_(
                                InspectionConfig.is_enabled == True,
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
        if not trigger or trigger.is_processed:
            return

        generator = ReportGenerator(db)
        report_id = await generator.generate_inspection_report(trigger_id)

        trigger.is_processed = True
        trigger.report_id = report_id

        report = await get_alive_by_id(db, Report, report_id)
        if report and trigger.alert_id:
            report.alert_id = trigger.alert_id

        await db.commit()

        logger.info(f"Generated report {report_id} for trigger {trigger_id}")
