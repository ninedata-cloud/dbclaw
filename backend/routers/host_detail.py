from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
import logging
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models.host import Host
from backend.models.host_metric import HostMetric
from backend.models.soft_delete import get_alive_by_id
from backend.dependencies import get_current_user, get_current_admin
from backend.schemas.host_detail import (
    HostSummaryResponse,
    HostProcessItem,
    HostConnectionItem,
    HostNetworkTopologyResponse
)
from backend.services.ssh_connection_pool import get_ssh_pool
from backend.services.host_process_service import HostProcessService
from backend.services.host_network_service import HostNetworkService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/host-detail",
    tags=["host-detail"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/{host_id}/summary", response_model=HostSummaryResponse)
async def get_host_summary(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机概览信息"""
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    # 获取最新指标
    metric_result = await db.execute(
        select(HostMetric)
        .where(HostMetric.host_id == host_id)
        .order_by(desc(HostMetric.collected_at))
        .limit(1)
    )
    latest_metric = metric_result.scalar_one_or_none()

    # 构建响应
    host_dict = {
        "id": host.id,
        "name": host.name,
        "host": host.host,
        "port": host.port,
        "username": host.username,
        "auth_type": host.auth_type,
        "os_version": host.os_version,
        "created_at": host.created_at,
        "updated_at": host.updated_at
    }

    latest_metric_dict = None
    if latest_metric:
        latest_metric_dict = {
            "cpu_usage": latest_metric.cpu_usage,
            "memory_usage": latest_metric.memory_usage,
            "disk_usage": latest_metric.disk_usage,
            "collected_at": latest_metric.collected_at,
            "data": latest_metric.data
        }

    # 尝试获取进程数和连接数（可选，失败不影响主流程）
    process_count = None
    connection_count = None
    uptime_seconds = None

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            # 获取进程数
            processes = await HostProcessService.get_processes(ssh_client)
            process_count = len(processes)

            # 获取连接数
            connections = await HostNetworkService.get_connections(ssh_client)
            connection_count = len(connections)

            # 获取运行时间
            if latest_metric_dict and latest_metric_dict.get("data"):
                boot_time_str = latest_metric_dict["data"].get("boot_time")
                if boot_time_str:
                    try:
                        boot_time = datetime.fromisoformat(boot_time_str.replace('Z', '+00:00'))
                        uptime_seconds = int((datetime.utcnow() - boot_time).total_seconds())
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Failed to get additional host info for {host_id}: {e}")

    return HostSummaryResponse(
        host=host_dict,
        latest_metric=latest_metric_dict,
        process_count=process_count,
        connection_count=connection_count,
        uptime_seconds=uptime_seconds
    )


@router.get("/{host_id}/metrics")
async def get_host_metrics(
    host_id: int,
    minutes: int = 60,
    db: AsyncSession = Depends(get_db)
):
    """获取主机历史指标（用于图表）"""
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    # 查询指定时间范围内的指标
    start_time = datetime.utcnow() - timedelta(minutes=minutes)

    result = await db.execute(
        select(HostMetric)
        .where(HostMetric.host_id == host_id)
        .where(HostMetric.collected_at >= start_time)
        .order_by(HostMetric.collected_at)
        .limit(1000)
    )
    metrics = result.scalars().all()

    # 转换为前端需要的格式
    return [
        {
            "collected_at": metric.collected_at.isoformat(),
            "cpu_usage": metric.cpu_usage,
            "memory_usage": metric.memory_usage,
            "disk_usage": metric.disk_usage,
            "data": metric.data
        }
        for metric in metrics
    ]


@router.get("/{host_id}/processes", response_model=List[HostProcessItem])
async def get_host_processes(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机实时进程列表"""
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            processes = await HostProcessService.get_processes(ssh_client)
            return [HostProcessItem(**p) for p in processes]
    except Exception as e:
        logger.error(f"Failed to get processes for host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"获取进程列表失败: {str(e)}")


@router.post("/{host_id}/processes/{pid}/kill")
async def kill_host_process(
    host_id: int,
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """终止主机进程（需管理员权限）"""
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            success = await HostProcessService.kill_process(ssh_client, pid)
            if success:
                return {"success": True, "message": f"进程 {pid} 已终止"}
            else:
                raise HTTPException(status_code=500, detail="终止进程失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to kill process {pid} on host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"终止进程失败: {str(e)}")


@router.get("/{host_id}/connections", response_model=List[HostConnectionItem])
async def get_host_connections(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机网络连接列表"""
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            connections = await HostNetworkService.get_connections(ssh_client)
            return [HostConnectionItem(**c) for c in connections]
    except Exception as e:
        logger.error(f"Failed to get connections for host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"获取网络连接失败: {str(e)}")


@router.get("/{host_id}/network-topology", response_model=HostNetworkTopologyResponse)
async def get_host_network_topology(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机网络拓扑数据（聚合）"""
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            connections = await HostNetworkService.get_connections(ssh_client)

            # 聚合连接数据
            aggregated = HostNetworkService.aggregate_connections(connections)

            # 统计各状态连接数
            stats = {
                "total_connections": len(connections),
                "established": sum(1 for c in connections if c['state'] == 'ESTAB' or c['state'] == 'ESTABLISHED'),
                "time_wait": sum(1 for c in connections if 'TIME_WAIT' in c['state']),
                "listen": sum(1 for c in connections if 'LISTEN' in c['state'])
            }

            host_dict = {
                "id": host.id,
                "name": host.name,
                "host": host.host,
                "port": host.port
            }

            return HostNetworkTopologyResponse(
                host=host_dict,
                connections=aggregated,
                stats=stats
            )
    except Exception as e:
        logger.error(f"Failed to get network topology for host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"获取网络拓扑失败: {str(e)}")
