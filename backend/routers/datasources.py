from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.schemas.datasource import (
    DatasourceCreate, DatasourceUpdate, DatasourceResponse, DatasourceTestResult, DatasourceTestRequest
)
from backend.utils.encryption import encrypt_value, decrypt_value
from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/datasources", tags=["datasources"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[DatasourceResponse])
async def list_datasources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Datasource).order_by(Datasource.id.desc()))
    return result.scalars().all()


@router.post("", response_model=DatasourceResponse)
async def create_datasource(data: DatasourceCreate, db: AsyncSession = Depends(get_db)):
    datasource = Datasource(
        name=data.name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        username=data.username,
        password_encrypted=encrypt_value(data.password) if data.password else None,
        database=data.database,
        host_id=data.host_id,
        extra_params=data.extra_params,
        importance_level=data.importance_level,
        monitoring_interval=data.monitoring_interval,
    )
    db.add(datasource)
    await db.commit()
    await db.refresh(datasource)
    return datasource


@router.get("/{datasource_id}", response_model=DatasourceResponse)
async def get_datasource(datasource_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return datasource


@router.put("/{datasource_id}", response_model=DatasourceResponse)
async def update_datasource(datasource_id: int, data: DatasourceUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        pwd = update_data.pop("password")
        if pwd is not None:
            datasource.password_encrypted = encrypt_value(pwd)

    for key, value in update_data.items():
        setattr(datasource, key, value)

    await db.commit()
    await db.refresh(datasource)
    return datasource


@router.delete("/{datasource_id}")
async def delete_datasource(datasource_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")
    await db.delete(datasource)
    await db.commit()
    return {"message": "Datasource deleted"}


@router.post("/test", response_model=DatasourceTestResult)
async def test_datasource_connection(data: DatasourceTestRequest, db: AsyncSession = Depends(get_db)):
    """Test database connection with provided parameters (without saving to database)"""
    try:
        from backend.services.db_connector import get_connector

        password = data.password

        # If datasource_id is provided and password is None, use saved password
        if data.datasource_id is not None and password is None:
            result = await db.execute(select(Datasource).where(Datasource.id == data.datasource_id))
            datasource = result.scalar_one_or_none()
            if datasource and datasource.password_encrypted:
                password = decrypt_value(datasource.password_encrypted)

        connector = get_connector(
            db_type=data.db_type,
            host=data.host,
            port=data.port,
            username=data.username,
            password=password,
            database=data.database,
        )
        version = await connector.test_connection()
        return DatasourceTestResult(success=True, message="Connection successful", version=version)
    except Exception as e:
        logger.error(f"Failed to test connection to {data.host}:{data.port}: {e}", exc_info=True)
        return DatasourceTestResult(success=False, message=str(e))


@router.post("/{datasource_id}/test", response_model=DatasourceTestResult)
async def test_datasource(datasource_id: int, db: AsyncSession = Depends(get_db)):
    """Test database connection using saved datasource configuration"""
    result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    try:
        from backend.services.db_connector import get_connector
        password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
        connector = get_connector(
            db_type=datasource.db_type,
            host=datasource.host,
            port=datasource.port,
            username=datasource.username,
            password=password,
            database=datasource.database,
        )
        version = await connector.test_connection()
        return DatasourceTestResult(success=True, message="Connection successful", version=version)
    except Exception as e:
        logger.error(f"Failed to test datasource {datasource_id} ({datasource.name}): {e}", exc_info=True)
        return DatasourceTestResult(success=False, message=str(e))
