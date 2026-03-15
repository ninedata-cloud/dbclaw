import json
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.system_config import SystemConfig


async def get_config(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Retrieve and parse configuration value"""
    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.key == key,
            SystemConfig.is_active == True
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return default
    return _parse_value(config.value, config.value_type)


async def get_all_configs(db: AsyncSession, category: Optional[str] = None) -> List[SystemConfig]:
    """List configurations"""
    query = select(SystemConfig).where(SystemConfig.is_active == True)
    if category:
        query = query.where(SystemConfig.category == category)
    result = await db.execute(query)
    return result.scalars().all()


async def set_config(
    db: AsyncSession,
    key: str,
    value: str,
    value_type: str,
    description: Optional[str] = None,
    category: Optional[str] = None
) -> SystemConfig:
    """Create or update configuration"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()

    if config:
        config.value = value
        config.value_type = value_type
        if description is not None:
            config.description = description
        if category is not None:
            config.category = category
    else:
        config = SystemConfig(
            key=key,
            value=value,
            value_type=value_type,
            description=description,
            category=category
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)
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
