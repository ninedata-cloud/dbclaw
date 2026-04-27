from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from backend.database import get_db
from backend.models.host import Host
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.schemas.host import (
    HostCreate, HostUpdate, HostResponse, SSHTestResult
)
from backend.utils.encryption import encrypt_value, decrypt_value
from backend.dependencies import get_current_user
from backend.utils.datetime_helper import to_utc_isoformat, now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hosts", tags=["hosts"], dependencies=[Depends(get_current_user)])


async def _get_os_version_via_ssh(host: str, port: int, username: str, password: str = None, private_key: str = None, use_agent: bool = False) -> str | None:
    """通过 SSH 获取操作系统版本"""
    try:
        from backend.services.ssh_service import SSHService
        ssh = SSHService(
            host=host,
            port=port,
            username=username,
            password=password,
            private_key=private_key,
            use_agent=use_agent,
        )
        # 尝试获取 OS 版本信息
        output = ssh.execute("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME || uname -a")
        if output:
            # 解析 PRETTY_NAME=xxx 格式
            for line in output.strip().split('\n'):
                if 'PRETTY_NAME' in line:
                    return line.split('=')[1].strip().strip('"')
            return output.strip()[:255]  # fallback to uname output
    except Exception as e:
        logger.warning(f"Failed to get OS version for {host}: {e}")
    return None


def _build_ssh_service(*, host: str, port: int, username: str, password: str = None, private_key: str = None, auth_type: str = "password"):
    from backend.services.ssh_service import SSHService
    return SSHService(
        host=host,
        port=port,
        username=username,
        password=password,
        private_key=private_key,
        use_agent=(auth_type == "agent"),
    )


@router.get("", response_model=List[HostResponse])
async def list_host(db: AsyncSession = Depends(get_db)):
    from backend.models.host_metric import HostMetric
    from sqlalchemy import desc
    from datetime import datetime, timezone

    result = await db.execute(alive_select(Host).order_by(Host.id.desc()))
    hosts = result.scalars().all()

    response = []
    for host in hosts:
        host_dict = {
            "id": host.id,
            "name": host.name,
            "host": host.host,
            "port": host.port,
            "username": host.username,
            "auth_type": host.auth_type,
            "os_version": host.os_version,
            "created_at": host.created_at,
            "updated_at": host.updated_at,
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "status": "unknown",
            "status_message": None,
            "last_check_time": None
        }

        # Get latest metrics from host_metric
        metric_result = await db.execute(
            select(HostMetric)
            .where(HostMetric.host_id == host.id)
            .order_by(desc(HostMetric.collected_at))
            .limit(1)
        )
        metric = metric_result.scalar_one_or_none()

        if metric:
            host_dict["cpu_usage"] = metric.cpu_usage
            host_dict["memory_usage"] = metric.memory_usage
            host_dict["disk_usage"] = metric.disk_usage
            host_dict["last_check_time"] = metric.collected_at

            # Determine status based on metrics and freshness
            # Use UTC to match PostgreSQL server_default=func.now() which returns UTC
            current_time = now()
            metric_time = metric.collected_at
            metric_age = (current_time - metric_time).total_seconds()

            # If metrics are older than 5 minutes, consider offline
            if metric_age > 300:
                host_dict["status"] = "offline"
                host_dict["status_message"] = "连接失败（超过5分钟未收到数据）"
            else:
                # Check for warnings/errors
                issues = []
                cpu = metric.cpu_usage or 0
                mem = metric.memory_usage or 0
                disk = metric.disk_usage or 0

                if cpu >= 90:
                    issues.append(f"CPU使用率过高 ({cpu:.1f}%)")
                elif cpu >= 80:
                    issues.append(f"CPU使用率较高 ({cpu:.1f}%)")

                if mem >= 90:
                    issues.append(f"内存使用率过高 ({mem:.1f}%)")
                elif mem >= 80:
                    issues.append(f"内存使用率较高 ({mem:.1f}%)")

                if disk >= 90:
                    issues.append(f"磁盘使用率过高 ({disk:.1f}%)")
                elif disk >= 80:
                    issues.append(f"磁盘使用率较高 ({disk:.1f}%)")

                if issues:
                    # Determine severity
                    has_critical = any([cpu >= 90, mem >= 90, disk >= 90])
                    host_dict["status"] = "critical" if has_critical else "warning"
                    host_dict["status_message"] = "；".join(issues)
                else:
                    host_dict["status"] = "normal"
                    host_dict["status_message"] = "运行正常"
        else:
            # No metrics yet
            host_dict["status"] = "offline"
            host_dict["status_message"] = "暂无监控数据"

        response.append(host_dict)

    return response


@router.post("", response_model=HostResponse)
async def create_host(data: HostCreate, db: AsyncSession = Depends(get_db)):
    host = Host(
        name=data.name,
        host=data.host,
        port=data.port,
        username=data.username,
        auth_type=data.auth_type,
        password_encrypted=encrypt_value(data.password) if data.password else None,
        private_key_encrypted=encrypt_value(data.private_key) if data.private_key else None,
    )
    db.add(host)
    await db.commit()
    await db.refresh(host)

    # 获取 OS 版本信息
    try:
        os_version = await _get_os_version_via_ssh(
            host=data.host,
            port=data.port,
            username=data.username,
            password=data.password,
            private_key=data.private_key,
            use_agent=(data.auth_type == "agent"),
        )
        if os_version:
            host.os_version = os_version
            await db.commit()
            await db.refresh(host)
    except Exception as e:
        logger.warning(f"Failed to get OS version for host {host.name}: {e}")

    # Immediately collect metrics for the new host
    try:
        from backend.services.host_collector import _collect_host_metric
        await _collect_host_metric(host)
        logger.info(f"Collected initial metrics for new host {host.name}")
    except Exception as e:
        logger.warning(f"Failed to collect initial metrics for host {host.name}: {e}")

    return host


@router.put("/{host_id}", response_model=HostResponse)
async def update_host(host_id: int, data: HostUpdate, db: AsyncSession = Depends(get_db)):
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        pwd = update_data.pop("password")
        if pwd is not None:
            host.password_encrypted = encrypt_value(pwd)
    if "private_key" in update_data:
        pk = update_data.pop("private_key")
        if pk is not None:
            host.private_key_encrypted = encrypt_value(pk)

    for key, value in update_data.items():
        setattr(host, key, value)

    # 如果连接参数变化，重新获取 OS 版本
    connection_params_changed = any(k in update_data for k in ['host', 'port', 'username', 'password', 'private_key', 'auth_type'])
    if connection_params_changed:
        try:
            password = update_data.get('password')
            if password is None and data.password is None:
                password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
            private_key = update_data.get('private_key')
            if private_key is None and data.private_key is None:
                private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None

            os_version = await _get_os_version_via_ssh(
                host=update_data.get('host', host.host),
                port=update_data.get('port', host.port),
                username=update_data.get('username', host.username),
                password=password,
                private_key=private_key,
                use_agent=(update_data.get('auth_type', host.auth_type) == "agent"),
            )
            if os_version:
                host.os_version = os_version
        except Exception as e:
            logger.warning(f"Failed to get OS version after updating host {host.name}: {e}")

    await db.commit()
    await db.refresh(host)

    # Immediately collect metrics after update
    try:
        from backend.services.host_collector import _collect_host_metric
        await _collect_host_metric(host)
        logger.info(f"Collected metrics after updating host {host.name}")
    except Exception as e:
        logger.warning(f"Failed to collect metrics after update for host {host.name}: {e}")

    return host


@router.delete("/{host_id}")
async def delete_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")
    host.soft_delete(current_user.id)
    await db.commit()
    return {"message": "SSH host deleted"}


@router.get("/{host_id}/summary")
async def get_host_summary(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机摘要信息，包括基本信息和最新指标"""
    from backend.models.host_metric import HostMetric
    from sqlalchemy import desc

    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    # 获取最新指标
    metric_result = await db.execute(
        select(HostMetric)
        .where(HostMetric.host_id == host_id)
        .order_by(desc(HostMetric.collected_at))
        .limit(1)
    )
    metric = metric_result.scalar_one_or_none()

    # 从 metric.data 中提取 uptime_seconds
    uptime_seconds = None
    if metric and metric.data:
        uptime_seconds = metric.data.get("uptime_seconds")

    return {
        "host": {
            "id": host.id,
            "name": host.name,
            "host": host.host,
            "port": host.port,
            "username": host.username,
            "auth_type": host.auth_type,
            "os_version": host.os_version,
            "created_at": host.created_at,
            "updated_at": host.updated_at,
        },
        "latest_metric": {
            "cpu_usage": metric.cpu_usage,
            "memory_usage": metric.memory_usage,
            "disk_usage": metric.disk_usage,
            "collected_at": metric.collected_at,
        } if metric else None,
        "uptime_seconds": uptime_seconds,
    }


@router.get("/{host_id}/metrics")
async def get_host_metric(
    host_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """获取主机历史指标数据"""
    from backend.models.host_metric import HostMetric
    from sqlalchemy import desc
    from datetime import datetime, timedelta

    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    # 查询指定时间范围内的指标
    start_time = now() - timedelta(hours=hours)
    result = await db.execute(
        select(HostMetric)
        .where(
            HostMetric.host_id == host_id,
            HostMetric.collected_at >= start_time
        )
        .order_by(HostMetric.collected_at)
    )
    metrics = result.scalars().all()

    return {
        "host_id": host_id,
        "metrics": [
            {
                "collected_at": to_utc_isoformat(m.collected_at),
                "cpu_usage": m.cpu_usage,
                "memory_usage": m.memory_usage,
                "disk_usage": m.disk_usage,
            }
            for m in metrics
        ]
    }


@router.get("/{host_id}/network-topology")
async def get_host_network_topology(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机网络拓扑数据"""
    from backend.services.ssh_connection_pool import get_ssh_pool
    from backend.services.host_network_service import HostNetworkService

    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            connections = await HostNetworkService.get_connections(ssh_client)
            aggregated = HostNetworkService.aggregate_connections(connections)

            return {
                "host": {
                    "id": host.id,
                    "name": host.name,
                    "host": host.host,
                },
                "connections": aggregated,
                "total_count": len(connections)
            }
    except Exception as e:
        logger.error(f"Failed to get network topology for host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get network topology: {str(e)}")


@router.get("/{host_id}/processes")
async def get_host_processes(host_id: int, db: AsyncSession = Depends(get_db)):
    """获取主机进程列表"""
    from backend.services.ssh_connection_pool import get_ssh_pool
    from backend.services.host_process_service import HostProcessService

    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            processes = await HostProcessService.get_processes(ssh_client)
            return processes
    except Exception as e:
        logger.error(f"Failed to get processes for host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get processes: {str(e)}")


@router.get("/{host_id}/processes/{pid}")
async def get_process_detail(host_id: int, pid: int, db: AsyncSession = Depends(get_db)):
    """获取进程详细信息"""
    from backend.services.ssh_connection_pool import get_ssh_pool
    from backend.services.host_process_service import HostProcessService

    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    try:
        ssh_pool = get_ssh_pool()
        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            detail = await HostProcessService.get_process_detail(ssh_client, pid)
            return detail
    except Exception as e:
        logger.error(f"Failed to get process detail for host {host_id}, pid {pid}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get process detail: {str(e)}")


@router.post("/test", response_model=SSHTestResult)
async def test_host_connection(data: HostCreate):
    try:
        ssh = _build_ssh_service(
            host=data.host,
            port=data.port,
            username=data.username,
            password=data.password,
            private_key=data.private_key,
            auth_type=data.auth_type,
        )
        output = ssh.execute("echo 'SSH connection successful'")
        return SSHTestResult(success=True, message=output.strip())
    except Exception as e:
        logger.error(f"Failed to test SSH host {data.host}:{data.port} ({data.username}): {e}", exc_info=True)
        return SSHTestResult(success=False, message=str(e))


@router.post("/{host_id}/test", response_model=SSHTestResult)
async def test_host(host_id: int, db: AsyncSession = Depends(get_db)):
    host = await get_alive_by_id(db, Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    try:
        password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
        private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
        ssh = _build_ssh_service(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password,
            private_key=private_key,
            auth_type=host.auth_type,
        )
        output = ssh.execute("echo 'SSH connection successful'")

        # 更新 OS 版本信息
        try:
            os_version = await _get_os_version_via_ssh(
                host=host.host,
                port=host.port,
                username=host.username,
                password=password,
                private_key=private_key,
                use_agent=(host.auth_type == "agent"),
            )
            if os_version:
                host.os_version = os_version
                await db.commit()
                await db.refresh(host)
        except Exception as e:
            logger.warning(f"Failed to update OS version for host {host.name}: {e}")

        # Immediately collect metrics after successful test
        try:
            from backend.services.host_collector import _collect_host_metric
            await _collect_host_metric(host)
            logger.info(f"Collected metrics after testing host {host.name}")
        except Exception as e:
            logger.warning(f"Failed to collect metrics after test for host {host.name}: {e}")

        return SSHTestResult(success=True, message=output.strip())
    except Exception as e:
        logger.error(f"Failed to test SSH host {host_id} ({host.name}): {e}", exc_info=True)
        return SSHTestResult(success=False, message=str(e))
