import json
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.system_config import SystemConfig
from backend.utils.encryption import encrypt_value, decrypt_value

MASKED_VALUE = "****"


async def get_config(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Retrieve and parse configuration value, auto-decrypting if encrypted"""
    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.key == key,
            SystemConfig.is_active == True
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return default
    value = config.value
    if config.is_encrypted and value:
        value = decrypt_value(value)
    return _parse_value(value, config.value_type)


async def get_all_configs(db: AsyncSession, category: Optional[str] = None) -> List[SystemConfig]:
    """List configurations, decrypting encrypted values"""
    query = select(SystemConfig).where(SystemConfig.is_active == True)
    if category:
        query = query.where(SystemConfig.category == category)
    result = await db.execute(query)
    configs = result.scalars().all()
    for config in configs:
        if config.is_encrypted and config.value:
            config.value = decrypt_value(config.value)
    return configs


async def set_config(
    db: AsyncSession,
    key: str,
    value: str,
    value_type: str,
    description: Optional[str] = None,
    category: Optional[str] = None,
    is_encrypted: bool = False
) -> SystemConfig:
    """Create or update configuration, encrypting value if is_encrypted=True"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()

    stored_value = encrypt_value(value) if is_encrypted and value else value

    if config:
        config.value = stored_value
        config.value_type = value_type
        config.is_encrypted = is_encrypted
        if description is not None:
            config.description = description
        if category is not None:
            config.category = category
    else:
        config = SystemConfig(
            key=key,
            value=stored_value,
            value_type=value_type,
            description=description,
            category=category,
            is_encrypted=is_encrypted
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)
    # Decrypt value before returning
    if config.is_encrypted and config.value:
        config.value = decrypt_value(config.value)
    return config


async def delete_config(db: AsyncSession, key: str) -> bool:
    """Soft delete configuration"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    if not config:
        return False
    config.is_active = False
    await db.commit()
    return True


def _parse_value(value: str, value_type: str) -> Any:
    """Parse string value to appropriate type with error handling"""
    try:
        if value_type == "string":
            return value
        elif value_type == "integer":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "boolean":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "json":
            return json.loads(value)
        else:
            return value
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot convert value '{value}' to {value_type}: {str(e)}")
