"""
Migration: backfill remaining legacy alert channel data and drop obsolete schema.
"""

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
        alert_channels_exists = await _table_exists(conn, "alert_channels")
        subscriptions_exists = await _table_exists(conn, "alert_subscription")
        execution_logs_exists = await _table_exists(conn, "integration_execution_log")

        channels = {}
        if alert_channels_exists:
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

        if subscriptions_exists and channels:
            has_channel_ids = await _column_exists(conn, "alert_subscription", "channel_ids")
            has_targets = await _column_exists(conn, "alert_subscription", "integration_targets")
            if has_channel_ids and has_targets:
                subscription_result = await conn.execute(
                    text(
                        """
                        SELECT id, channel_ids, integration_targets
                        FROM alert_subscription
                        """
                    )
                )
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

        if execution_logs_exists and channels:
            if await _column_exists(conn, "integration_execution_log", "channel_id"):
                log_result = await conn.execute(
                    text(
                        """
                        SELECT id, channel_id, target_type, target_ref, target_name, params_snapshot
                        FROM integration_execution_log
                        WHERE channel_id IS NOT NULL
                        """
                    )
                )
                for row in log_result.fetchall():
                    channel = channels.get(row.channel_id)
                    if not channel:
                        continue

                    target_type = row.target_type or "legacy_alert_channel"
                    target_ref = row.target_ref or str(channel["id"])
                    target_name = row.target_name or channel["name"]
                    params_snapshot = _load_json_value(row.params_snapshot) or channel["params"]

                    await conn.execute(
                        text(
                            """
                            UPDATE integration_execution_log
                            SET target_type = :target_type,
                                target_ref = :target_ref,
                                target_name = :target_name,
                                params_snapshot = CAST(:params_snapshot AS JSON)
                            WHERE id = :log_id
                            """
                        ),
                        {
                            "target_type": target_type,
                            "target_ref": target_ref,
                            "target_name": target_name,
                            "params_snapshot": json.dumps(params_snapshot, ensure_ascii=False),
                            "log_id": row.id,
                        },
                    )

        if execution_logs_exists and await _column_exists(conn, "integration_execution_log", "channel_id"):
            await conn.execute(
                text(
                    """
                    ALTER TABLE integration_execution_log
                    DROP COLUMN IF EXISTS channel_id
                    """
                )
            )

        if subscriptions_exists and await _column_exists(conn, "alert_subscription", "channel_ids"):
            await conn.execute(
                text(
                    """
                    ALTER TABLE alert_subscription
                    DROP COLUMN IF EXISTS channel_ids
                    """
                )
            )

        if alert_channels_exists:
            await conn.execute(text("DROP TABLE IF EXISTS alert_channels"))

        logger.info("Dropped legacy alert channel schema")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
