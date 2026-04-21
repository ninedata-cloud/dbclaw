"""Migration: copy alert_channels/channel_ids into subscription.integration_targets."""

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


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none() is not None


async def migrate():
    async with engine.begin() as conn:
        if not await _table_exists(conn, "alert_subscription"):
            return
        if not await _table_exists(conn, "alert_channels"):
            return
        if not await _column_exists(conn, "alert_subscription", "channel_ids"):
            return
        if not await _column_exists(conn, "alert_subscription", "integration_targets"):
            return

        channel_result = await conn.execute(
            text(
                """
                SELECT id, name, integration_id, enabled, params
                FROM alert_channels
                """
            )
        )
        channels = {
            row.id: {
                "id": row.id,
                "name": row.name,
                "integration_id": row.integration_id,
                "enabled": row.enabled,
                "params": _load_json_value(row.params) or {},
            }
            for row in channel_result.fetchall()
        }

        if not channels:
            return

        subscription_result = await conn.execute(
            text(
                """
                SELECT id, channel_ids, integration_targets
                FROM alert_subscription
                """
            )
        )

        migrated = 0
        for row in subscription_result.fetchall():
            integration_targets = _load_json_value(row.integration_targets) or []
            if integration_targets:
                continue

            channel_ids = _load_json_value(row.channel_ids) or []
            if not isinstance(channel_ids, list) or not channel_ids:
                continue

            targets = []
            for channel_id in channel_ids:
                try:
                    channel = channels.get(int(channel_id))
                except (TypeError, ValueError):
                    channel = None
                if not channel:
                    continue
                targets.append(
                    {
                        "target_id": f"migrated-channel-{channel['id']}",
                        "integration_id": channel["integration_id"],
                        "name": channel["name"],
                        "enabled": channel["enabled"],
                        "notify_on": ["alert", "recovery"],
                        "params": channel["params"],
                    }
                )

            if not targets:
                continue

            await conn.execute(
                text(
                    """
                    UPDATE alert_subscription
                    SET integration_targets = CAST(:integration_targets AS JSON)
                    WHERE id = :subscription_id
                    """
                ),
                {
                    "integration_targets": json.dumps(targets, ensure_ascii=False),
                    "subscription_id": row.id,
                },
            )
            migrated += 1

        logger.info("Migrated %s subscriptions from channel_ids to integration_targets", migrated)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
