import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import async_session
from backend.services.config_service import get_config

logger = logging.getLogger(__name__)

MONITORING_COLLECTION_INTERVAL_CONFIG_KEY = "monitoring_collection_interval_seconds"
MIN_MONITORING_COLLECTION_INTERVAL_SECONDS = 5
MAX_MONITORING_COLLECTION_INTERVAL_SECONDS = 3600
DEFAULT_MONITORING_COLLECTION_INTERVAL_SECONDS = 60


def is_monitoring_collection_interval_config(key: Optional[str]) -> bool:
    return key == MONITORING_COLLECTION_INTERVAL_CONFIG_KEY


def normalize_monitoring_collection_interval_seconds(value, fallback: Optional[int] = None) -> int:
    default_value = fallback or get_settings().metric_interval or DEFAULT_MONITORING_COLLECTION_INTERVAL_SECONDS
    try:
        interval = int(value)
    except (TypeError, ValueError):
        interval = int(default_value)

    if interval < MIN_MONITORING_COLLECTION_INTERVAL_SECONDS or interval > MAX_MONITORING_COLLECTION_INTERVAL_SECONDS:
        raise ValueError(
            f"全局监控采集周期必须在 {MIN_MONITORING_COLLECTION_INTERVAL_SECONDS}-{MAX_MONITORING_COLLECTION_INTERVAL_SECONDS} 秒之间"
        )

    return interval


async def get_monitoring_collection_interval_seconds(
    db: AsyncSession,
    fallback: Optional[int] = None,
) -> int:
    default_value = fallback or get_settings().metric_interval or DEFAULT_MONITORING_COLLECTION_INTERVAL_SECONDS
    try:
        configured_value = await get_config(
            db,
            MONITORING_COLLECTION_INTERVAL_CONFIG_KEY,
            default=default_value,
        )
        return normalize_monitoring_collection_interval_seconds(configured_value, default_value)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("读取全局监控采集周期失败，回退默认值: %s", exc)
        return normalize_monitoring_collection_interval_seconds(default_value, default_value)


async def refresh_monitoring_schedulers(trigger_now: bool = False) -> int:
    async with async_session() as db:
        interval_seconds = await get_monitoring_collection_interval_seconds(db)

    from backend.services.metric_collector import start_scheduler
    from backend.services.integration_scheduler import refresh_scheduler as refresh_integration_scheduler

    start_scheduler(interval_seconds)
    await refresh_integration_scheduler(interval_seconds, trigger_now=trigger_now)
    return interval_seconds
