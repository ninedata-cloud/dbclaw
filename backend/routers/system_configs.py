from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from backend.database import get_db
from backend.dependencies import get_current_admin
from backend.models.user import User
from backend.models.system_config import SystemConfig
from backend.schemas.system_config import SystemConfigCreate, SystemConfigUpdate, SystemConfigResponse
from backend.services import config_service
from backend.i18n.errors import ApiError
from backend.i18n.locale import (
    DEFAULT_LOCALE,
    DEFAULT_TIMEZONE,
    normalize_locale,
    normalize_timezone,
    set_system_defaults,
    message_payload,
)
from backend.services.monitoring_scheduler_service import (
    is_monitoring_collection_interval_config,
    normalize_monitoring_collection_interval_seconds,
    refresh_monitoring_schedulers,
)

router = APIRouter(prefix="/api/system-configs", tags=["system-configs"])


def _validate_special_config(key: str, value: Optional[str], value_type: Optional[str]):
    if key == "i18n.default_locale" and value is not None and not normalize_locale(value):
        raise ApiError(400, "auth.locale_invalid", {"locale": value})
    if key == "i18n.default_timezone" and value is not None and not normalize_timezone(value):
        raise ApiError(400, "auth.timezone_invalid", {"timezone": value})
    if not is_monitoring_collection_interval_config(key):
        return

    if value_type is not None and value_type != "integer":
        raise ApiError(400, "request.validation.invalid")

    if value is not None:
        try:
            normalize_monitoring_collection_interval_seconds(value)
        except ValueError as exc:
            raise ApiError(400, "request.validation.invalid") from exc


async def _refresh_i18n_defaults(db: AsyncSession) -> None:
    set_system_defaults(
        await config_service.get_config(db, "i18n.default_locale", DEFAULT_LOCALE),
        await config_service.get_config(db, "i18n.default_timezone", DEFAULT_TIMEZONE),
    )


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
        raise ApiError(404, "config.not_found")
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
        if data.key.startswith("i18n.default_"):
            await _refresh_i18n_defaults(db)
        return config
    except IntegrityError:
        raise ApiError(400, "operation.not_allowed")


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
        raise ApiError(404, "config.not_found")

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
    if config.key.startswith("i18n.default_"):
        await _refresh_i18n_defaults(db)
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
        raise ApiError(404, "config.not_found")

    config.is_active = False
    await db.commit()
    if is_monitoring_collection_interval_config(config.key):
        await refresh_monitoring_schedulers()
    if config.key.startswith("i18n.default_"):
        await _refresh_i18n_defaults(db)
    return message_payload("config.deleted")
