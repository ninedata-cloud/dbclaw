from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from backend.database import get_db
from backend.dependencies import get_current_admin
from backend.models.user import User
from backend.models.system_config import SystemConfig
from backend.schemas.system_config import SystemConfigCreate, SystemConfigUpdate, SystemConfigResponse
from backend.services import config_service
from backend.services.monitoring_scheduler_service import (
    is_monitoring_collection_interval_config,
    normalize_monitoring_collection_interval_seconds,
    refresh_monitoring_schedulers,
)

router = APIRouter(prefix="/api/system-configs", tags=["system-configs"])


def _validate_special_config(key: str, value: Optional[str], value_type: Optional[str]):
    if not is_monitoring_collection_interval_config(key):
        return

    if value_type is not None and value_type != "integer":
        raise HTTPException(status_code=400, detail="全局监控采集周期必须使用整数类型")

    if value is not None:
        try:
            normalize_monitoring_collection_interval_seconds(value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[SystemConfigResponse])
async def list_configs(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all configurations"""
    configs = await config_service.get_all_configs(db, category)
    return configs


@router.get("/{id}", response_model=SystemConfigResponse)
async def get_config(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get single configuration"""
    config = await db.get(SystemConfig, id)
    if not config or not config.is_active:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return config


@router.post("", response_model=SystemConfigResponse)
async def create_config(
    data: SystemConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create new configuration"""
    _validate_special_config(data.key, data.value, data.value_type)
    try:
        config = await config_service.set_config(
            db, data.key, data.value, data.value_type, data.description, data.category, data.is_encrypted
        )
        if is_monitoring_collection_interval_config(data.key):
            await refresh_monitoring_schedulers()
        return config
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Configuration key already exists")


@router.put("/{id}", response_model=SystemConfigResponse)
async def update_config(
    id: int,
    data: SystemConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update configuration"""
    from backend.utils.encryption import encrypt_value
    config = await db.get(SystemConfig, id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    _validate_special_config(config.key, data.value, data.value_type)

    if data.is_encrypted is not None:
        config.is_encrypted = data.is_encrypted
    if data.value is not None:
        # If value is non-empty, store it (encrypting if needed)
        if data.value != "":
            config.value = encrypt_value(data.value) if config.is_encrypted else data.value
        # If value is empty string and field is encrypted, keep existing encrypted value
    if data.value_type is not None:
        config.value_type = data.value_type
    if data.description is not None:
        config.description = data.description
    if data.category is not None:
        config.category = data.category
    if data.is_active is not None:
        config.is_active = data.is_active

    await db.commit()
    await db.refresh(config)
    if is_monitoring_collection_interval_config(config.key):
        await refresh_monitoring_schedulers()
    # Decrypt value before returning
    if config.is_encrypted and config.value:
        from backend.utils.encryption import decrypt_value
        config.value = decrypt_value(config.value)
    return config


@router.delete("/{id}")
async def delete_config(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Soft delete configuration by setting is_active=False"""
    config = await db.get(SystemConfig, id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    config.is_active = False
    await db.commit()
    if is_monitoring_collection_interval_config(config.key):
        await refresh_monitoring_schedulers()
    return {"message": "Configuration deleted successfully"}
