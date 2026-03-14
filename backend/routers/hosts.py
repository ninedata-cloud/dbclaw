from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from backend.database import get_db
from backend.models.host import Host
from backend.schemas.host import (
    HostCreate, HostUpdate, HostResponse, SSHTestResult
)
from backend.utils.encryption import encrypt_value, decrypt_value
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/hosts", tags=["hosts"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[HostResponse])
async def list_hosts(db: AsyncSession = Depends(get_db)):
    from backend.models.host_metric import HostMetric
    from sqlalchemy import desc

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
            "cpu_usage": None
        }

        # Get latest CPU usage from host_metrics
        metric_result = await db.execute(
            select(HostMetric)
            .where(HostMetric.host_id == host.id)
            .order_by(desc(HostMetric.collected_at))
            .limit(1)
        )
        metric = metric_result.scalar_one_or_none()
        if metric:
            host_dict["cpu_usage"] = metric.cpu_usage

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
        ssh = SSHService(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password,
            private_key=private_key,
        )
        output = ssh.execute("echo 'SSH connection successful'")
        return SSHTestResult(success=True, message=output.strip())
    except Exception as e:
        return SSHTestResult(success=False, message=str(e))
