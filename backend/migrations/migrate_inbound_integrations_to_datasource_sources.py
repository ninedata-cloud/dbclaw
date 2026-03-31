"""
Migration: populate datasource.inbound_source from enabled inbound integrations.
"""

import asyncio
import logging
from sqlalchemy import select
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    from backend.models.datasource import Datasource
    from backend.models.integration import Integration

    async with async_session() as db:
        result = await db.execute(select(Integration).where(Integration.integration_type == 'inbound_metric', Integration.enabled == True))
        integrations = result.scalars().all()
        if len(integrations) != 1:
            logger.warning("Expected exactly one enabled inbound_metric integration for automatic migration, found %s", len(integrations))
            return

        integration = integrations[0]
        default_params = {}
        properties = (integration.config_schema or {}).get('properties') or {}
        for key, prop in properties.items():
            if isinstance(prop, dict) and 'default' in prop:
                default_params[key] = prop.get('default')

        ds_result = await db.execute(select(Datasource).where(Datasource.metric_source == 'integration'))
        datasources = ds_result.scalars().all()
        migrated = 0
        for ds in datasources:
            if ds.inbound_source:
                continue
            ds.inbound_source = {
                "integration_id": integration.id,
                "enabled": True,
                "params": default_params,
                "schedule": {"mode": "interval", "seconds": 60}
            }
            migrated += 1

        await db.commit()
        logger.info("Migrated %s datasources to inbound_source", migrated)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
