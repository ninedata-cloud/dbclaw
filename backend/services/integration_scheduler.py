"""
集成调度器

定期执行 inbound_metric 类型的集成，采集外部监控数据
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models.integration import Integration, IntegrationExecutionLog
from backend.models.datasource import Datasource
from backend.models.soft_delete import get_alive_by_id, alive_filter
from backend.services.integration_executor import IntegrationExecutor
from backend.services.metric_collector import _push_to_subscribers
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


async def execute_integration(datasource_id: int):
    """
    按数据源执行 inbound_metric 集成。
    """
    from datetime import datetime as dt
    start_time = dt.now()
    execution_log = None
    integration = None

    async with async_session() as session:
        try:
            datasource = await get_alive_by_id(session, Datasource, datasource_id)
            if not datasource or not datasource.is_active:
                logger.warning(f"数据源 {datasource_id} 不存在或未启用")
                return

            inbound_source = datasource.inbound_source or {}
            if datasource.metric_source != 'integration' or not inbound_source.get('enabled', True):
                return

            integration_id = inbound_source.get('integration_id')
            if not integration_id:
                logger.warning(f"数据源 {datasource_id} 未配置 inbound_source.integration_id")
                return

            integration = await get_alive_by_id(session, Integration, int(integration_id))
            if not integration or not integration.enabled:
                logger.warning(f"集成 {integration_id} 不存在或未启用")
                return

            if integration.integration_type != 'inbound_metric':
                return

            execution_log = IntegrationExecutionLog(
                integration_id=integration.id,
                target_type='inbound_source',
                target_ref=str(datasource.id),
                datasource_id=datasource.id,
                target_name=datasource.name,
                params_snapshot=inbound_source.get('params') or {},
                trigger_source='scheduler',
                status='pending'
            )
            session.add(execution_log)
            await session.commit()
            await session.refresh(execution_log)

            datasource_list = [{
                "id": datasource.id,
                "name": datasource.name,
                "db_type": datasource.db_type,
                "host": datasource.host,
                "port": datasource.port,
                "database": datasource.database,
                "external_instance_id": datasource.external_instance_id
            }]

            executor = IntegrationExecutor(session, logger)
            params = inbound_source.get('params') or {}
            metrics = await executor.execute_metric_collection(integration.code, params, datasource_list)

            if metrics:
                from backend.models.metric_snapshot import MetricSnapshot
                current_time = dt.now()
                metric_data = {}
                for metric in metrics:
                    if metric.get('datasource_id') != datasource.id:
                        continue
                    if 'metric_name' not in metric or 'metric_value' not in metric:
                        continue
                    metric_data[metric['metric_name']] = metric['metric_value']

                if metric_data:
                    result = await session.execute(
                        select(MetricSnapshot)
                        .where(and_(MetricSnapshot.datasource_id == datasource.id, MetricSnapshot.metric_type == "db_status"))
                        .order_by(desc(MetricSnapshot.collected_at))
                        .limit(1)
                    )
                    latest_snapshot = result.scalar_one_or_none()
                    merged_data = dict(latest_snapshot.data) if latest_snapshot and latest_snapshot.data else {}
                    # 避免覆盖系统直连采集到的指标（如连接数/bytes_received 等），集成数据只补充缺失项
                    for k, v in metric_data.items():
                        if k not in merged_data:
                            merged_data[k] = v
                    snapshot = MetricSnapshot(
                        datasource_id=datasource.id,
                        metric_type="db_status",
                        data=merged_data,
                        collected_at=current_time
                    )
                    session.add(snapshot)
                    await session.commit()

                    await _push_to_subscribers(
                        datasource.id,
                        {
                            "type": "db_status",
                            "datasource_id": datasource.id,
                            "data": snapshot.data,
                            "collected_at": snapshot.collected_at.isoformat(),
                        },
                    )

            execution_log.status = 'success'
            execution_log.result = {"datasource_count": 1, "metric_count": len(metrics)}
            execution_log.execution_time_ms = int((dt.now() - start_time).total_seconds() * 1000)
            execution_log.payload_summary = {"datasource_id": datasource.id}
            integration.last_run_at = now()
            integration.last_error = None
            await session.commit()

        except Exception as e:
            error_msg = f"集成执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if execution_log:
                execution_log.status = 'failed'
                execution_log.error_message = error_msg
                execution_log.execution_time_ms = int((dt.now() - start_time).total_seconds() * 1000)
            if integration:
                integration.last_error = error_msg
                integration.last_run_at = now()
            await session.commit()


async def schedule_all_integrations():
    """按数据源调度所有启用的 inbound_metric 配置"""
    global scheduler

    if scheduler is None:
        scheduler = AsyncIOScheduler()
        scheduler.start()
        logger.info("集成调度器已启动")

    async with async_session() as session:
        result = await session.execute(
            select(Datasource).where(
                and_(
                    Datasource.metric_source == 'integration',
                    Datasource.is_active == True,
                    alive_filter(Datasource)
                )
            )
        )
        datasources = result.scalars().all()
        logger.info(f"找到 {len(datasources)} 个启用的入站集成数据源")

        for datasource in datasources:
            inbound_source = datasource.inbound_source or {}
            if not inbound_source.get('integration_id') or not inbound_source.get('enabled', True):
                continue

            interval_seconds = ((inbound_source.get('schedule') or {}).get('seconds')) or 60
            job_id = f"integration_ds_{datasource.id}"

            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

            scheduler.add_job(
                execute_integration,
                'interval',
                seconds=interval_seconds,
                args=[datasource.id],
                id=job_id,
                replace_existing=True
            )

            logger.info(f"已调度入站集成数据源: {datasource.name} (每 {interval_seconds} 秒)")

            # 立即执行一次
            asyncio.create_task(execute_integration(datasource.id))


async def start_integration_scheduler():
    """启动集成调度器"""
    logger.info("正在启动集成调度器...")
    await schedule_all_integrations()
    logger.info("集成调度器启动完成")


def stop_integration_scheduler():
    """停止集成调度器"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("集成调度器已停止")
