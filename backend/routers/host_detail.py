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
    HostNetworkTopologyResponse,
    HostConfigResponse
)
from backend.services.ssh_connection_pool import get_ssh_pool
from backend.utils.datetime_helper import to_utc_isoformat
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
            "collected_at": to_utc_isoformat(metric.collected_at),
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


@router.get("/{host_id}/config", response_model=HostConfigResponse)
async def get_host_config(
    host_id: int,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """获取主机系统配置信息

    Args:
        host_id: 主机ID
        force_refresh: 是否强制刷新（忽略缓存）
    """
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")

    # 如果有缓存且未过期（24小时内），直接返回
    if not force_refresh and host.config_data and host.config_collected_at:
        cache_age = (datetime.utcnow() - host.config_collected_at).total_seconds()
        if cache_age < 86400:  # 24小时
            logger.info(f"返回主机 {host_id} 的缓存配置（{cache_age:.0f}秒前采集）")
            return HostConfigResponse(
                **host.config_data,
                collected_at=host.config_collected_at
            )

    # 实时采集配置
    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            import asyncio
            loop = asyncio.get_event_loop()

            def _execute_commands():
                """执行多个系统命令获取配置信息"""
                commands = {
                    # CPU 信息
                    'cpu_model': "cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d: -f2 | xargs",
                    'cpu_cores': "nproc",
                    'cpu_physical': "cat /proc/cpuinfo | grep 'physical id' | sort -u | wc -l",
                    'cpu_mhz': "cat /proc/cpuinfo | grep 'cpu MHz' | head -1 | cut -d: -f2 | xargs",

                    # 内存信息
                    'memory_info': "cat /proc/meminfo | grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree):'",

                    # 磁盘信息
                    'disk_info': "df -h | grep -v tmpfs | grep -v devtmpfs",
                    'disk_io': "cat /proc/diskstats | awk '{print $3, $4, $8}'",

                    # 网络接口信息
                    'network_interfaces': "ip -o addr show | awk '{print $2, $3, $4}'",
                    'network_stats': "cat /proc/net/dev | tail -n +3",

                    # 系统信息
                    'kernel': "uname -r",
                    'os_release': "cat /etc/os-release 2>/dev/null || echo 'NAME=Unknown'",
                    'hostname': "hostname",
                    'uptime': "cat /proc/uptime | awk '{print $1}'",
                    'load_avg': "cat /proc/loadavg",
                }

                results = {}
                for key, cmd in commands.items():
                    try:
                        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=10)
                        output = stdout.read().decode('utf-8', errors='replace').strip()
                        results[key] = output
                    except Exception as e:
                        logger.warning(f"Failed to execute {key}: {e}")
                        results[key] = ""

                return results

            raw_data = await loop.run_in_executor(None, _execute_commands)

            # 解析 CPU 信息
            cpu_info = {
                "model": raw_data.get('cpu_model', 'Unknown'),
                "cores": int(raw_data.get('cpu_cores', '0') or '0'),
                "physical_cpus": int(raw_data.get('cpu_physical', '0') or '0'),
                "mhz": raw_data.get('cpu_mhz', 'Unknown'),
            }

            # 解析内存信息
            memory_lines = raw_data.get('memory_info', '').split('\n')
            memory_info = {}
            for line in memory_lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    memory_info[key.strip()] = value.strip()

            # 解析磁盘信息
            disk_lines = raw_data.get('disk_info', '').split('\n')
            disk_info = []
            for i, line in enumerate(disk_lines):
                if i == 0:  # 跳过表头
                    continue
                parts = line.split()
                if len(parts) >= 6:
                    disk_info.append({
                        "filesystem": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "use_percent": parts[4],
                        "mounted_on": parts[5]
                    })

            # 解析网络接口信息
            network_lines = raw_data.get('network_interfaces', '').split('\n')
            network_info = []
            seen_interfaces = set()
            for line in network_lines:
                parts = line.split()
                if len(parts) >= 3:
                    iface = parts[0]
                    if iface not in seen_interfaces:
                        network_info.append({
                            "interface": iface,
                            "family": parts[1],
                            "address": parts[2]
                        })
                        seen_interfaces.add(iface)

            # 解析系统信息
            os_release_lines = raw_data.get('os_release', '').split('\n')
            os_name = "Unknown"
            os_version = ""
            for line in os_release_lines:
                if line.startswith('NAME='):
                    os_name = line.split('=', 1)[1].strip('"')
                elif line.startswith('VERSION='):
                    os_version = line.split('=', 1)[1].strip('"')

            uptime_seconds = 0
            try:
                uptime_seconds = int(float(raw_data.get('uptime', '0')))
            except:
                pass

            load_avg_parts = raw_data.get('load_avg', '').split()
            system_info = {
                "kernel": raw_data.get('kernel', 'Unknown'),
                "os_name": os_name,
                "os_version": os_version,
                "hostname": raw_data.get('hostname', 'Unknown'),
                "uptime_seconds": uptime_seconds,
                "load_avg_1": load_avg_parts[0] if len(load_avg_parts) > 0 else "0",
                "load_avg_5": load_avg_parts[1] if len(load_avg_parts) > 1 else "0",
                "load_avg_15": load_avg_parts[2] if len(load_avg_parts) > 2 else "0",
            }

            config_response = HostConfigResponse(
                cpu=cpu_info,
                memory=memory_info,
                disk=disk_info,
                network=network_info,
                system=system_info,
                collected_at=datetime.utcnow()
            )

            # 自动保存到数据库
            host.config_data = config_response.model_dump(exclude={'collected_at'})
            host.config_collected_at = config_response.collected_at
            await db.commit()
            logger.info(f"已保存主机 {host_id} 的配置到数据库")

            return config_response

    except Exception as e:
        logger.error(f"Failed to get host config for {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"获取主机配置失败: {str(e)}")


@router.post("/{host_id}/config/refresh", response_model=HostConfigResponse)
async def refresh_host_config(host_id: int, db: AsyncSession = Depends(get_db)):
    """强制刷新主机配置（重新采集并保存）"""
    return await get_host_config(host_id, force_refresh=True, db=db)
