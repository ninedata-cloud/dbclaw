"""
集成调度器

定期执行 inbound_metric 类型的集成，采集外部监控数据
"""

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_, desc

from backend.database import async_session
from backend.models.integration import Integration, IntegrationExecutionLog
from backend.models.datasource import Datasource
from backend.models.soft_delete import get_alive_by_id, alive_filter
from backend.services.integration_executor import IntegrationExecutor
from backend.services.datasource_metric_merge import (
    cleanup_obsolete_integration_keys,
    merge_integration_metric_data,
)
from backend.services.metric_collector import _push_to_subscribers
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None
GLOBAL_INTEGRATION_JOB_ID = "integration_global_collector"


async def _collect_direct_metrics_supplement(datasource: Datasource) -> dict:
    """
    补充采集云 API 不提供的关键字段（max_connections、uptime、cache_hit_rate 等）

    Args:
        datasource: 数据源对象

    Returns:
        补充的指标字典
    """
    from backend.services.db_connector import get_connector
    from backend.utils.encryption import decrypt_value

    supplement = {}
    connector = None

    try:
        password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
        connector = get_connector(
            db_type=datasource.db_type,
            host=datasource.host,
            port=datasource.port,
            username=datasource.username,
            password=password,
            database=datasource.database,
            extra_params=datasource.extra_params,
        )

        status = await connector.get_status()

        # 只提取云 API 不提供的字段
        if 'max_connections' in status:
            supplement['max_connections'] = status['max_connections']
        if 'uptime' in status:
            supplement['uptime'] = status['uptime']
        if 'cache_hit_rate' in status:
            supplement['cache_hit_rate'] = status['cache_hit_rate']
        if 'buffer_pool_hit_rate' in status:
            supplement['buffer_pool_hit_rate'] = status['buffer_pool_hit_rate']

    except Exception as e:
        logger.warning(f"补充采集数据源 {datasource.id} 失败: {e}")
    finally:
        if connector is not None:
            try:
                await connector.close()
            except Exception:
                pass

    return supplement



def _ensure_scheduler_started():
    global scheduler

    if scheduler is None:
        scheduler = AsyncIOScheduler()
        scheduler.start()
        logger.info("集成调度器已启动")


async def refresh_scheduler(interval_seconds: Optional[int] = None, trigger_now: bool = False):
    """按全局监控采集周期刷新外部集成调度任务。"""
    _ensure_scheduler_started()

    if interval_seconds is None:
        from backend.services.monitoring_scheduler_service import get_monitoring_collection_interval_seconds

        async with async_session() as session:
            interval_seconds = await get_monitoring_collection_interval_seconds(session)

    scheduler.add_job(
        execute_all_integration,
        'interval',
        seconds=interval_seconds,
        id=GLOBAL_INTEGRATION_JOB_ID,
        replace_existing=True
    )
    logger.info("已刷新全局入站集成调度任务: 每 %s 秒", interval_seconds)

    if trigger_now:
        asyncio.create_task(execute_all_integration())


async def sync_datasource_schedule(datasource_id: int, trigger_now: bool = True):
    """
    兼容旧调用入口：
    - 刷新全局集成调度
    - 可选立即执行当前数据源一次外部指标采集
    """
    await refresh_scheduler(trigger_now=False)
    if trigger_now:
        asyncio.create_task(execute_integration(datasource_id))


async def unschedule_datasource(datasource_id: int):
    """兼容旧调用入口：删除数据源后刷新全局集成调度。"""
    await refresh_scheduler(trigger_now=False)


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
            if not integration or not integration.is_enabled:
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
                from backend.models.datasource_metric import DatasourceMetric
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
                        select(DatasourceMetric)
                        .where(and_(DatasourceMetric.datasource_id == datasource.id, DatasourceMetric.metric_type == "db_status"))
                        .order_by(desc(DatasourceMetric.collected_at))
                        .limit(1)
                    )
                    latest_snapshot = result.scalar_one_or_none()
                    merged_data = merge_integration_metric_data(
                        latest_snapshot.data if latest_snapshot and latest_snapshot.data else {},
                        metric_data,
                    )
                    merged_data = cleanup_obsolete_integration_keys(datasource.db_type, merged_data)

                    # 补充直连采集的关键字段（max_connections、uptime、cache_hit_rate 等）
                    # 这些字段会强制覆盖集成采集的值，因为直连采集更准确
                    logger.info(f"[补充采集] 开始补充采集数据源 {datasource.id}")
                    direct_metrics = await _collect_direct_metrics_supplement(datasource)
                    logger.info(f"[补充采集] 数据源 {datasource.id} 补充采集结果: {direct_metrics}")
                    if direct_metrics:
                        for key, value in direct_metrics.items():
                            logger.info(f"[补充采集] 覆盖字段 {key}: {merged_data.get(key)} -> {value}")
                            merged_data[key] = value  # 强制覆盖
                    snapshot = DatasourceMetric(
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


async def execute_all_integration():
    """按全局采集周期执行所有启用的 inbound_metric 数据源。"""
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
        datasource = result.scalars().all()
        datasource_ids = [
            datasource.id
            for datasource in datasource
            if (datasource.inbound_source or {}).get('integration_id')
            and (datasource.inbound_source or {}).get('enabled', True)
        ]

    if not datasource_ids:
        logger.debug("当前没有启用的入站集成数据源")
        return

    logger.info("开始执行 %s 个入站集成数据源的全局采集任务", len(datasource_ids))
    await asyncio.gather(
        *(execute_integration(datasource_id) for datasource_id in datasource_ids),
        return_exceptions=True,
    )


async def schedule_all_integration():
    """兼容旧调用入口：刷新全局入站集成调度。"""
    await refresh_scheduler(trigger_now=True)


async def start_integration_scheduler():
    """启动集成调度器"""
    logger.info("正在启动集成调度器...")
    await refresh_scheduler(trigger_now=True)
    logger.info("集成调度器启动完成")


def stop_integration_scheduler():
    """停止集成调度器"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("集成调度器已停止")
