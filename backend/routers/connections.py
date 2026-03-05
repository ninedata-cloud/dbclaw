from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from backend.database import get_db
from backend.models.connection import Connection
from backend.schemas.connection import (
    ConnectionCreate, ConnectionUpdate, ConnectionResponse, ConnectionTestResult
)
from backend.utils.encryption import encrypt_value, decrypt_value

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("", response_model=List[ConnectionResponse])
async def list_connections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection).order_by(Connection.id.desc()))
    return result.scalars().all()


@router.post("", response_model=ConnectionResponse)
async def create_connection(data: ConnectionCreate, db: AsyncSession = Depends(get_db)):
    conn = Connection(
        name=data.name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        username=data.username,
        password_encrypted=encrypt_value(data.password) if data.password else None,
        database=data.database,
        ssh_host_id=data.ssh_host_id,
        extra_params=data.extra_params,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


@router.get("/{conn_id}", response_model=ConnectionResponse)
async def get_connection(conn_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection).where(Connection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.put("/{conn_id}", response_model=ConnectionResponse)
async def update_connection(conn_id: int, data: ConnectionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection).where(Connection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        pwd = update_data.pop("password")
        if pwd is not None:
            conn.password_encrypted = encrypt_value(pwd)

    for key, value in update_data.items():
        setattr(conn, key, value)

    await db.commit()
    await db.refresh(conn)
    return conn


@router.delete("/{conn_id}")
async def delete_connection(conn_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection).where(Connection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()
    return {"message": "Connection deleted"}


@router.post("/{conn_id}/test", response_model=ConnectionTestResult)
async def test_connection(conn_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection).where(Connection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    try:
        from backend.services.db_connector import get_connector
        password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None
        connector = get_connector(
            db_type=conn.db_type,
            host=conn.host,
            port=conn.port,
            username=conn.username,
            password=password,
            database=conn.database,
        )
        version = await connector.test_connection()
        return ConnectionTestResult(success=True, message="Connection successful", version=version)
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))
