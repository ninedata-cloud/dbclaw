"""
Migration: convert legacy integration_metric snapshots into db_status snapshots.
"""

import asyncio
import json
import logging
from collections import defaultdict

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
        if not await _table_exists(conn, "datasource_metric"):
            return

        legacy_result = await conn.execute(
            text(
                """
                SELECT id, datasource_id, collected_at, data
                FROM datasource_metric
                WHERE metric_type = 'integration_metric'
                ORDER BY datasource_id, collected_at, id
                """
            )
        )
        legacy_rows = legacy_result.fetchall()
        if not legacy_rows:
            return

        grouped: dict[tuple[int, object], dict] = defaultdict(dict)
        row_ids: list[int] = []
        for row in legacy_rows:
            payload = _load_json_value(row.data) or {}
            metric_name = payload.get("metric_name")
            metric_value = payload.get("value")
            if metric_name and metric_value is not None:
                grouped[(row.datasource_id, row.collected_at)][metric_name] = metric_value
            row_ids.append(row.id)

        inserted = 0
        updated = 0
        for (datasource_id, collected_at), metric_data in grouped.items():
            if not metric_data:
                continue

            existing_result = await conn.execute(
                text(
                    """
                    SELECT id, data
                    FROM datasource_metric
                    WHERE datasource_id = :datasource_id
                      AND metric_type = 'db_status'
                      AND collected_at = :collected_at
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"datasource_id": datasource_id, "collected_at": collected_at},
            )
            existing = existing_result.first()

            if existing:
                merged = _load_json_value(existing.data) or {}
                merged.update(metric_data)
                await conn.execute(
                    text(
                        """
                        UPDATE datasource_metric
                        SET data = CAST(:data AS JSON)
                        WHERE id = :snapshot_id
                        """
                    ),
                    {
                        "data": json.dumps(merged, ensure_ascii=False),
                        "snapshot_id": existing.id,
                    },
                )
                updated += 1
                continue

            await conn.execute(
                text(
                    """
                    INSERT INTO datasource_metric (datasource_id, metric_type, data, collected_at)
                    VALUES (:datasource_id, 'db_status', CAST(:data AS JSON), :collected_at)
                    """
                ),
                {
                    "datasource_id": datasource_id,
                    "data": json.dumps(metric_data, ensure_ascii=False),
                    "collected_at": collected_at,
                },
            )
            inserted += 1

        await conn.execute(
            text(
                """
                DELETE FROM datasource_metric
                WHERE metric_type = 'integration_metric'
                """
            )
        )

        logger.info(
            "Migrated legacy integration_metric snapshots: inserted=%s updated=%s deleted=%s",
            inserted,
            updated,
            len(row_ids),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
