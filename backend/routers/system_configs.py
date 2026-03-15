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

router = APIRouter(prefix="/api/system-configs", tags=["system-configs"])


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
    try:
        config = await config_service.set_config(
            db, data.key, data.value, data.value_type, data.description, data.category
        )
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
    config = await db.get(SystemConfig, id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if data.value is not None:
        config.value = data.value
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
    return {"message": "Configuration deleted successfully"}
