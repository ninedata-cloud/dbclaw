"""
Migration: promote Feishu bot channel config into integration_bot_bindings.
"""

import asyncio
import logging
from sqlalchemy import select, desc
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    from backend.models.integration import Integration, AlertChannel
    from backend.models.integration_bot_binding import IntegrationBotBinding

    async with async_session() as db:
        result = await db.execute(select(Integration).where(Integration.integration_id == 'builtin_feishu_bot'))
        integration = result.scalar_one_or_none()
        if not integration:
            logger.warning('builtin_feishu_bot not found, skipping bot binding migration')
            return

        existing_result = await db.execute(select(IntegrationBotBinding).where(IntegrationBotBinding.code == 'feishu_bot'))
        if existing_result.scalar_one_or_none():
            logger.info('feishu_bot binding already exists')
            return

        channel_result = await db.execute(
            select(AlertChannel)
            .where(AlertChannel.integration_id == integration.id, AlertChannel.enabled == True)
            .order_by(desc(AlertChannel.updated_at))
            .limit(1)
        )
        channel = channel_result.scalar_one_or_none()
        if not channel:
            logger.warning('No enabled alert channel found for builtin_feishu_bot')
            return

        binding = IntegrationBotBinding(
            integration_id=integration.id,
            code='feishu_bot',
            name=channel.name or '飞书机器人',
            enabled=channel.enabled,
            params=channel.params or {}
        )
        db.add(binding)
        await db.commit()
        logger.info('Migrated Feishu bot channel to integration_bot_bindings')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
