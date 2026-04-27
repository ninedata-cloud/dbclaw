"""
主机知识上下文服务
为 AI 诊断提供主机相关的上下文信息
"""
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.datasource import Datasource
from backend.models.host import Host
from backend.models.host_metric import HostMetric
from backend.models.soft_delete import alive_select, get_alive_by_id
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)


async def build_host_knowledge_context(db: AsyncSession, host_id: int) -> dict[str, Any]:
    """
    构建主机诊断所需的上下文信息

    返回结构:
    {
        "host_info": {...},  # 主机基本信息
        "latest_metrics": {...},  # 最新指标
        "metric_trends": [...],  # 指标趋势（最近1小时）
        "top_processes": [...],  # TOP 进程
        "network_summary": {...},  # 网络连接摘要
        "related_datasource": [...],  # 关联的数据源
    }
    """
    # 1. 获取主机基本信息
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        logger.warning(f"Host {host_id} not found")
        return {}

    # 2. 获取最新指标
    latest_metric_result = await db.execute(
        select(HostMetric)
        .where(HostMetric.host_id == host_id)
        .order_by(desc(HostMetric.collected_at))
        .limit(1)
    )
    latest_metric = latest_metric_result.scalar_one_or_none()

    # 3. 获取指标趋势（最近1小时）
    one_hour_ago = now() - timedelta(hours=1)
    trend_result = await db.execute(
        select(HostMetric)
        .where(HostMetric.host_id == host_id)
        .where(HostMetric.collected_at >= one_hour_ago)
        .order_by(HostMetric.collected_at)
    )
    metric_trends = trend_result.scalars().all()

    # 4. 获取 TOP 进程（通过 SSH）
    top_processes = []
    network_summary = {}
    try:
        from backend.services.ssh_pool import get_ssh_pool
        from backend.services.host_process_service import HostProcessService
        from backend.services.host_network_service import HostNetworkService

        ssh_pool = get_ssh_pool()
        ssh_client = await ssh_pool.get_connection(host_id)

        if ssh_client:
            # 获取进程列表
            try:
                processes = await HostProcessService.get_processes(ssh_client)
                top_processes = processes[:10]  # TOP 10
            except Exception as e:
                logger.warning(f"Failed to get processes for host {host_id}: {e}")

            # 获取网络连接
            try:
                connections = await HostNetworkService.get_connections(ssh_client)
                aggregated = HostNetworkService.aggregate_connections(connections)
                network_summary = {
                    "total_connections": len(connections),
                    "aggregated_count": len(aggregated),
                    "top_remotes": aggregated[:5] if aggregated else [],
                }
            except Exception as e:
                logger.warning(f"Failed to get network for host {host_id}: {e}")
    except Exception as e:
        logger.warning(f"Failed to connect to host {host_id} via SSH: {e}")

    # 6. 获取关联的数据源
    datasource_result = await db.execute(
        alive_select(Datasource).where(Datasource.host_id == host_id)
    )
    related_datasource = datasource_result.scalars().all()

    return {
        "host_info": {
            "id": host.id,
            "name": host.name,
            "host": host.host,
            "port": host.port,
            "os_version": host.os_version,
        },
        "latest_metrics": {
            "cpu_usage": latest_metric.cpu_usage if latest_metric else None,
            "memory_usage": latest_metric.memory_usage if latest_metric else None,
            "disk_usage": latest_metric.disk_usage if latest_metric else None,
            "collected_at": latest_metric.collected_at.isoformat() if latest_metric and latest_metric.collected_at else None,
        } if latest_metric else None,
        "metric_trends": [
            {
                "cpu": m.cpu_usage,
                "memory": m.memory_usage,
                "disk": m.disk_usage,
                "time": m.collected_at.isoformat() if m.collected_at else None,
            }
            for m in metric_trends
        ],
        "top_processes": [
            {
                "pid": p.get("pid"),
                "user": p.get("user"),
                "cpu_percent": p.get("cpu_percent"),
                "memory_percent": p.get("memory_percent"),
                "command": p.get("command"),
            }
            for p in top_processes
        ],
        "network_summary": network_summary,
        "related_datasource": [
            {
                "id": ds.id,
                "name": ds.name,
                "db_type": ds.db_type,
                "connection_status": ds.connection_status,
            }
            for ds in related_datasource
        ],
    }
