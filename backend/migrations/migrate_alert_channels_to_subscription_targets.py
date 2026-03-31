"""
Migration: copy alert_channels/channel_ids into subscription.integration_targets.
"""

import asyncio
import logging
from sqlalchemy import select
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    from backend.models.alert_subscription import AlertSubscription
    from backend.models.integration import AlertChannel

    async with async_session() as db:
        result = await db.execute(select(AlertSubscription))
        subscriptions = result.scalars().all()
        migrated = 0

        for sub in subscriptions:
            if sub.integration_targets:
                continue

            targets = []
            for channel_id in (sub.channel_ids or []):
                channel = await db.get(AlertChannel, channel_id)
                if not channel:
                    continue
                targets.append({
                    "target_id": f"migrated-channel-{channel.id}",
                    "integration_id": channel.integration_id,
                    "name": channel.name,
                    "enabled": channel.enabled,
                    "notify_on": ["alert", "recovery"],
                    "params": channel.params or {}
                })

            if targets:
                sub.integration_targets = targets
                migrated += 1

        await db.commit()
        logger.info("Migrated %s subscriptions from channel_ids to integration_targets", migrated)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
