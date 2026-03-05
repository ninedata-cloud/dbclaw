from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from backend.database import get_db
from backend.models.ssh_host import SSHHost
from backend.schemas.ssh_host import (
    SSHHostCreate, SSHHostUpdate, SSHHostResponse, SSHTestResult
)
from backend.utils.encryption import encrypt_value, decrypt_value

router = APIRouter(prefix="/api/ssh-hosts", tags=["ssh-hosts"])


@router.get("", response_model=List[SSHHostResponse])
async def list_ssh_hosts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SSHHost).order_by(SSHHost.id.desc()))
    return result.scalars().all()


@router.post("", response_model=SSHHostResponse)
async def create_ssh_host(data: SSHHostCreate, db: AsyncSession = Depends(get_db)):
    host = SSHHost(
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


@router.put("/{host_id}", response_model=SSHHostResponse)
async def update_ssh_host(host_id: int, data: SSHHostUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SSHHost).where(SSHHost.id == host_id))
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
async def delete_ssh_host(host_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SSHHost).where(SSHHost.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="SSH host not found")
    await db.delete(host)
    await db.commit()
    return {"message": "SSH host deleted"}


@router.post("/{host_id}/test", response_model=SSHTestResult)
async def test_ssh_host(host_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SSHHost).where(SSHHost.id == host_id))
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
