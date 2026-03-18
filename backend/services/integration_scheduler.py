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
from backend.services.integration_executor import IntegrationExecutor
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


async def execute_integration(integration_id: int):
    """
    执行单个集成

    Args:
        integration_id: 集成 ID
    """
    from datetime import datetime as dt
    start_time = dt.now()
    execution_log = None

    async with async_session() as session:
        try:
            # 查询集成配置
            result = await session.execute(
                select(Integration).where(
                    and_(
                        Integration.id == integration_id,
                        Integration.enabled == True
                    )
                )
            )
            integration = result.scalar_one_or_none()

            if not integration:
                logger.warning(f"集成 {integration_id} 不存在或未启用")
                return

            # 只处理 inbound_metric 类型
            if integration.integration_type != 'inbound_metric':
                return

            logger.info(f"开始执行集成: {integration.name} (ID: {integration.id})")

            # 创建执行日志
            execution_log = IntegrationExecutionLog(
                integration_id=integration.id,
                trigger_source='scheduler',
                status='pending'
            )
            session.add(execution_log)
            await session.commit()
            await session.refresh(execution_log)

            # 查询使用此集成的数据源
            datasources_result = await session.execute(
                select(Datasource).where(
                    and_(
                        Datasource.metric_source == 'integration',
                        Datasource.is_active == True
                    )
                )
            )
            datasources = datasources_result.scalars().all()

            if not datasources:
                logger.info(f"集成 {integration.name} 没有关联的数据源")
                execution_log.status = 'success'
                execution_log.result = {"message": "没有关联的数据源"}
                execution_log.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                await session.commit()
                return

            # 准备数据源信息
            datasource_list = []
            for ds in datasources:
                datasource_list.append({
                    "id": ds.id,
                    "name": ds.name,
                    "db_type": ds.db_type,
                    "host": ds.host,
                    "port": ds.port,
                    "database": ds.database,
                    "external_instance_id": ds.external_instance_id
                })

            # 执行集成
            executor = IntegrationExecutor(session, logger)

            # 从集成的 config_schema 中提取默认参数
            params = {}
            if integration.config_schema and 'properties' in integration.config_schema:
                for key, prop in integration.config_schema['properties'].items():
                    if 'default' in prop:
                        params[key] = prop['default']

            metrics = await executor.execute_metric_collection(
                integration.code,
                params,
                datasource_list
            )

            logger.info(f"集成 {integration.name} 采集到 {len(metrics)} 个指标")

            # 写入指标数据
            if metrics:
                from backend.models.metric_snapshot import MetricSnapshot

                # 使用当前时间作为采集时间（而不是阿里云返回的历史时间戳）
                current_time = dt.now()

                # 按 datasource_id 分组指标
                metrics_by_ds = {}
                for metric in metrics:
                    # 验证必需字段
                    if 'datasource_id' not in metric or 'metric_name' not in metric or 'metric_value' not in metric:
                        logger.warning(f"跳过无效指标: {metric}")
                        continue

                    ds_id = metric['datasource_id']
                    if ds_id not in metrics_by_ds:
                        metrics_by_ds[ds_id] = {}

                    # 将指标添加到该数据源的字典中
                    metrics_by_ds[ds_id][metric['metric_name']] = metric['metric_value']

                # 为每个数据源创建或更新 db_status 快照
                snapshots = []
                for ds_id, metric_data in metrics_by_ds.items():
                    # 查询该数据源最新的 db_status 快照
                    result = await session.execute(
                        select(MetricSnapshot)
                        .where(
                            and_(
                                MetricSnapshot.datasource_id == ds_id,
                                MetricSnapshot.metric_type == "db_status"
                            )
                        )
                        .order_by(desc(MetricSnapshot.collected_at))
                        .limit(1)
                    )
                    latest_snapshot = result.scalar_one_or_none()

                    # 合并指标数据
                    if latest_snapshot and latest_snapshot.data:
                        # 如果有最新快照，合并数据
                        merged_data = dict(latest_snapshot.data)
                        merged_data.update(metric_data)
                    else:
                        # 如果没有最新快照，直接使用集成指标
                        merged_data = metric_data

                    # 创建新的 db_status 快照
                    snapshot = MetricSnapshot(
                        datasource_id=ds_id,
                        metric_type="db_status",  # 使用 db_status 类型，与前端兼容
                        data=merged_data,
                        collected_at=current_time
                    )
                    snapshots.append(snapshot)

                session.add_all(snapshots)
                await session.commit()
                logger.info(f"成功写入 {len(snapshots)} 个数据源的指标（共 {len(metrics)} 个指标）")

            # 更新执行日志
            execution_log.status = 'success'
            execution_log.result = {
                "datasource_count": len(datasources),
                "metric_count": len(metrics)
            }
            execution_log.execution_time_ms = int((dt.now() - start_time).total_seconds() * 1000)

            # 更新集成的最后运行时间
            integration.last_run_at = now()
            integration.last_error = None

            await session.commit()

            logger.info(f"集成 {integration.name} 执行成功")

        except Exception as e:
            error_msg = f"集成执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # 更新执行日志
            if execution_log:
                execution_log.status = 'failed'
                execution_log.error_message = error_msg
                execution_log.execution_time_ms = int((dt.now() - start_time).total_seconds() * 1000)

            # 更新集成的最后错误
            if integration:
                integration.last_error = error_msg
                integration.last_run_at = now()

            await session.commit()


async def schedule_all_integrations():
    """调度所有启用的 inbound_metric 集成"""
    global scheduler

    if scheduler is None:
        scheduler = AsyncIOScheduler()
        scheduler.start()
        logger.info("集成调度器已启动")

    async with async_session() as session:
        # 查询所有启用的 inbound_metric 集成
        result = await session.execute(
            select(Integration).where(
                and_(
                    Integration.integration_type == 'inbound_metric',
                    Integration.enabled == True
                )
            )
        )
        integrations = result.scalars().all()

        logger.info(f"找到 {len(integrations)} 个启用的监控集成")

        for integration in integrations:
            # 默认每 60 秒执行一次
            interval_seconds = 60

            # 添加定时任务
            job_id = f"integration_{integration.id}"

            # 移除旧任务（如果存在）
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

            # 添加新任务
            scheduler.add_job(
                execute_integration,
                'interval',
                seconds=interval_seconds,
                args=[integration.id],
                id=job_id,
                replace_existing=True
            )

            logger.info(f"已调度集成: {integration.name} (每 {interval_seconds} 秒)")

            # 立即执行一次
            asyncio.create_task(execute_integration(integration.id))


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
