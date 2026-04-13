import json
import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


async def _column_type(conn) -> str | None:
    result = await conn.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'datasources'
              AND column_name = 'extra_params'
            """
        )
    )
    return result.scalar_one_or_none()


def _normalize_extra_params(raw_value):
    if raw_value in (None, "", {}):
        return None

    if isinstance(raw_value, dict):
        return raw_value

    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {"legacy_value": stripped}
        if isinstance(parsed, dict):
            return parsed
        return {"legacy_value": parsed}

    return {"legacy_value": raw_value}


async def migrate():
    engine = get_engine()

    async with engine.begin() as conn:
        column_type = await _column_type(conn)
        if column_type is None:
            logger.info("datasources.extra_params column does not exist, skipping")
            return

        if column_type == "jsonb":
            logger.info("datasources.extra_params is already jsonb")
            return

        if column_type == "json":
            logger.info("Converting datasources.extra_params from json to jsonb")
            await conn.execute(
                text(
                    """
                    ALTER TABLE datasources
                    ALTER COLUMN extra_params TYPE JSONB
                    USING extra_params::jsonb
                    """
                )
            )
            return

        if column_type not in {"text", "character varying"}:
            logger.warning("Unhandled datasources.extra_params type %s, skipping conversion", column_type)
            return

        logger.info("Converting datasources.extra_params from text to jsonb")
        await conn.execute(text("ALTER TABLE datasources ADD COLUMN IF NOT EXISTS extra_params_tmp JSONB"))

        rows = await conn.execute(text("SELECT id, extra_params FROM datasources"))
        for datasource_id, raw_value in rows.fetchall():
            normalized = _normalize_extra_params(raw_value)
            await conn.execute(
                text("UPDATE datasources SET extra_params_tmp = CAST(:payload AS JSONB) WHERE id = :datasource_id"),
                {
                    "datasource_id": datasource_id,
                    "payload": json.dumps(normalized) if normalized is not None else None,
                },
            )

        await conn.execute(text("ALTER TABLE datasources DROP COLUMN extra_params"))
        await conn.execute(text("ALTER TABLE datasources RENAME COLUMN extra_params_tmp TO extra_params"))

    logger.info("datasources.extra_params converted to jsonb")
