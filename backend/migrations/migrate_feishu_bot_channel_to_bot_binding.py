"""Migration: promote Feishu bot channel config into integration_bot_bindings."""

import asyncio
import json
import logging

from sqlalchemy import text

from backend.database import engine

logger = logging.getLogger(__name__)


def _load_json_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


async def _table_exists(conn, table_name: str) -> bool:
    result = await conn.execute(
        text("SELECT to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    )
    return result.scalar_one_or_none() is not None


async def migrate():
    async with engine.begin() as conn:
        if not await _table_exists(conn, "integrations"):
            return
        if not await _table_exists(conn, "integration_bot_bindings"):
            return
        if not await _table_exists(conn, "alert_channels"):
            return

        integration_result = await conn.execute(
            text(
                """
                SELECT id
                FROM integrations
                WHERE integration_id = 'builtin_feishu_bot'
                LIMIT 1
                """
            )
        )
        integration_id = integration_result.scalar_one_or_none()
        if not integration_id:
            logger.warning('builtin_feishu_bot not found, skipping bot binding migration')
            return

        binding_result = await conn.execute(
            text(
                """
                SELECT 1
                FROM integration_bot_bindings
                WHERE code = 'feishu_bot'
                LIMIT 1
                """
            )
        )
        if binding_result.scalar_one_or_none():
            logger.info('feishu_bot binding already exists')
            return

        channel_result = await conn.execute(
            text(
                """
                SELECT name, enabled, params
                FROM alert_channels
                WHERE integration_id = :integration_id
                  AND enabled = TRUE
                ORDER BY updated_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"integration_id": integration_id},
        )
        channel = channel_result.first()
        if not channel:
            logger.warning('No enabled alert channel found for builtin_feishu_bot')
            return

        await conn.execute(
            text(
                """
                INSERT INTO integration_bot_bindings (integration_id, code, name, enabled, params)
                VALUES (:integration_id, 'feishu_bot', :name, :enabled, CAST(:params AS JSONB))
                """
            ),
            {
                "integration_id": integration_id,
                "name": channel.name or '飞书机器人',
                "enabled": channel.enabled,
                "params": json.dumps(_load_json_value(channel.params) or {}, ensure_ascii=False),
            },
        )
        logger.info('Migrated Feishu bot channel to integration_bot_bindings')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
