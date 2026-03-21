from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from backend.database import get_db
from backend.models.host import Host
from backend.schemas.host import (
    HostCreate, HostUpdate, HostResponse, SSHTestResult
)
from backend.utils.encryption import encrypt_value, decrypt_value
from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hosts", tags=["hosts"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[HostResponse])
async def list_hosts(db: AsyncSession = Depends(get_db)):
    from backend.models.host_metric import HostMetric
    from sqlalchemy import desc
    from datetime import datetime, timezone

    result = await db.execute(select(Host).order_by(Host.id.desc()))
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
            "created_at": host.created_at,
            "updated_at": host.updated_at,
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "status": "unknown",
            "status_message": None,
            "last_check_time": None
        }

        # Get latest metrics from host_metrics
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
            now = datetime.utcnow()
            metric_time = metric.collected_at
            metric_age = (now - metric_time).total_seconds()

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
                    host_dict["status"] = "error" if has_critical else "warning"
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

    # Immediately collect metrics for the new host
    try:
        from backend.services.host_collector import _collect_host_metrics
        await _collect_host_metrics(db, host)
        await db.commit()
        logger.info(f"Collected initial metrics for new host {host.name}")
    except Exception as e:
        logger.warning(f"Failed to collect initial metrics for host {host.name}: {e}")

    return host


@router.put("/{host_id}", response_model=HostResponse)
async def update_host(host_id: int, data: HostUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
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

    await db.commit()
    await db.refresh(host)

    # Immediately collect metrics after update
    try:
        from backend.services.host_collector import _collect_host_metrics
        await _collect_host_metrics(db, host)
        await db.commit()
        logger.info(f"Collected metrics after updating host {host.name}")
    except Exception as e:
        logger.warning(f"Failed to collect metrics after update for host {host.name}: {e}")

    return host


@router.delete("/{host_id}")
async def delete_host(host_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")
    await db.delete(host)
    await db.commit()
    return {"message": "SSH host deleted"}


@router.post("/{host_id}/test", response_model=SSHTestResult)
async def test_host(host_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")

    try:
        from backend.services.ssh_service import SSHService
        password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
        private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
        use_agent = (host.auth_type == "agent")
        ssh = SSHService(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password,
            private_key=private_key,
            use_agent=use_agent,
        )
        output = ssh.execute("echo 'SSH connection successful'")

        # Immediately collect metrics after successful test
        try:
            from backend.services.host_collector import _collect_host_metrics
            await _collect_host_metrics(db, host)
            await db.commit()
            logger.info(f"Collected metrics after testing host {host.name}")
        except Exception as e:
            logger.warning(f"Failed to collect metrics after test for host {host.name}: {e}")

        return SSHTestResult(success=True, message=output.strip())
    except Exception as e:
        logger.error(f"Failed to test SSH host {host_id} ({host.name}): {e}", exc_info=True)
        return SSHTestResult(success=False, message=str(e))
