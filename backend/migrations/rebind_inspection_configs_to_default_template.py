"""
Migration: bind all inspection configs to the default alert template and clear legacy per-instance alert settings.
"""

import asyncio
import logging

from backend.database import async_session
from backend.services.alert_template_service import (
    bind_default_template_to_all_inspection_config,
    ensure_default_alert_template,
)

logger = logging.getLogger(__name__)


async def migrate():
    async with async_session() as db:
        await ensure_default_alert_template(db)
        changed = await bind_default_template_to_all_inspection_config(db)
        logger.info(
            "Migration complete: rebound inspection configs to default template, changed=%s",
            changed,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
