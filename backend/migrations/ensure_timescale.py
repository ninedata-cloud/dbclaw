"""
将 datasource_metric、host_metric 纳入 TimescaleDB：复合主键、hypertable、压缩与可选保留策略。

幂等：可重复执行；无 Timescale 扩展时按配置仅告警或跳过后续步骤。
"""
from __future__ import annotations

import logging
import re
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.database import get_engine

logger = logging.getLogger(__name__)

# 环境变量中的 interval 文本（如 "7 days"），禁止注入
_SAFE_INTERVAL = re.compile(r"^[0-9a-zA-Z\s:.-]+$")


def _sanitize_interval(label: str, value: str, default: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return default
    if len(raw) > 80 or not _SAFE_INTERVAL.match(raw):
        logger.warning(
            "ensure_timescale: invalid %s interval %r; using default %r",
            label,
            raw,
            default,
        )
        return default
    return raw


def _is_postgres_url(url: str) -> bool:
    try:
        u = make_url(url)
    except Exception:
        return False
    return (u.get_driver_name() or "").split("+", 1)[0] in ("postgresql", "postgres")


async def _table_exists(conn, name: str) -> bool:
    r = await conn.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'public' AND table_name = :name
            )
            """
        ),
        {"name": name},
    )
    return bool(r.scalar())


async def _primary_key_columns(conn, table: str) -> list[str]:
    r = await conn.execute(
        text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_schema = kcu.constraint_schema
             AND tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = 'public'
              AND tc.table_name = :table
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """
        ),
        {"table": table},
    )
    return [row[0] for row in r.fetchall()]


async def _primary_key_constraint_name(conn, table: str) -> str | None:
    r = await conn.execute(
        text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            WHERE tc.table_schema = 'public'
              AND tc.table_name = :table
              AND tc.constraint_type = 'PRIMARY KEY'
            LIMIT 1
            """
        ),
        {"table": table},
    )
    row = r.fetchone()
    return row[0] if row else None


async def _is_hypertable(conn, table: str) -> bool:
    r = await conn.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1 FROM timescaledb_information.hypertables
              WHERE hypertable_schema = 'public' AND hypertable_name = :table
            )
            """
        ),
        {"table": table},
    )
    return bool(r.scalar())


async def _ensure_extension(conn) -> bool:
    settings = get_settings()
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        logger.info("ensure_timescale: timescaledb extension is available")
        return True
    except SQLAlchemyError as e:
        msg = (
            "Failed to CREATE EXTENSION timescaledb. "
            "Install the TimescaleDB package and set shared_preload_libraries to include 'timescaledb' "
            "in postgresql.conf (or pass -c shared_preload_libraries=timescaledb), then restart PostgreSQL. "
            f"Details: {e}"
        )
        if settings.timescale_require_extension:
            logger.error(msg)
            raise RuntimeError(msg) from e
        logger.warning("%s — skipping hypertable setup (timescale_require_extension=false)", msg)
        return False


async def _ensure_composite_pk(conn, table: str, time_col: str) -> None:
    cols = await _primary_key_columns(conn, table)
    if set(cols) == {"id", time_col}:
        return
    if cols != ["id"]:
        logger.warning(
            "ensure_timescale: unexpected PK on %s: %s — skipping PK alteration",
            table,
            cols,
        )
        return
    cname = await _primary_key_constraint_name(conn, table)
    if not cname:
        logger.warning("ensure_timescale: no PK constraint on %s", table)
        return
    await conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{cname}"'))
    await conn.execute(text(f'ALTER TABLE "{table}" ADD PRIMARY KEY (id, "{time_col}")'))
    logger.info("ensure_timescale: altered primary key on %s to (id, %s)", table, time_col)


async def _create_hypertable(conn, table: str, chunk_interval: str) -> None:
    if await _is_hypertable(conn, table):
        logger.info("ensure_timescale: %s is already a hypertable", table)
        return
    # 表名来自固定常量，勿拼接用户输入
    sql = text(
        f"""
        SELECT create_hypertable(
          '{table}'::regclass,
          'collected_at',
          chunk_time_interval => CAST(:chunk AS interval),
          migrate_data => TRUE,
          if_not_exists => TRUE
        )
        """
    )
    await conn.execute(sql, {"chunk": chunk_interval})
    logger.info("ensure_timescale: create_hypertable for %s (chunk %s)", table, chunk_interval)


async def _set_compression_datasource(conn) -> None:
    await conn.execute(
        text(
            """
            ALTER TABLE datasource_metric SET (
              timescaledb.compress,
              timescaledb.compress_segmentby = 'datasource_id, metric_type',
              timescaledb.compress_orderby = 'collected_at DESC'
            )
            """
        )
    )


async def _set_compression_host(conn) -> None:
    await conn.execute(
        text(
            """
            ALTER TABLE host_metric SET (
              timescaledb.compress,
              timescaledb.compress_segmentby = 'host_id',
              timescaledb.compress_orderby = 'collected_at DESC'
            )
            """
        )
    )


def _assert_metric_table(table: str) -> None:
    if table not in ("datasource_metric", "host_metric"):
        raise ValueError(f"unexpected table for Timescale policy: {table!r}")


async def _refresh_compression_policy(conn, table: str, compress_after: str) -> None:
    _assert_metric_table(table)
    try:
        await conn.execute(text(f"SELECT remove_compression_policy('{table}', if_exists => TRUE)"))
    except SQLAlchemyError as e:
        logger.debug("ensure_timescale: remove_compression_policy %s: %s", table, e)
    await conn.execute(
        text(f"SELECT add_compression_policy('{table}', CAST(:interval AS interval))"),
        {"interval": compress_after},
    )
    logger.info(
        "ensure_timescale: compression policy on %s for chunks older than %s",
        table,
        compress_after,
    )


async def _refresh_retention_policy(conn, table: str, retention: str) -> None:
    _assert_metric_table(table)
    try:
        await conn.execute(text(f"SELECT remove_retention_policy('{table}', if_exists => TRUE)"))
    except SQLAlchemyError as e:
        logger.debug("ensure_timescale: remove_retention_policy %s: %s", table, e)
    await conn.execute(
        text(f"SELECT add_retention_policy('{table}', CAST(:interval AS interval))"),
        {"interval": retention},
    )
    logger.info(
        "ensure_timescale: retention policy on %s for data older than %s",
        table,
        retention,
    )


async def _clear_retention_if_disabled(conn, table: str) -> None:
    _assert_metric_table(table)
    try:
        await conn.execute(text(f"SELECT remove_retention_policy('{table}', if_exists => TRUE)"))
    except SQLAlchemyError:
        pass


async def upgrade() -> None:
    settings = get_settings()
    if not settings.timescale_enable:
        logger.info("ensure_timescale: skipped (timescale_enable=false)")
        return
    if not _is_postgres_url(settings.database_url):
        logger.info("ensure_timescale: skipped (non-PostgreSQL DATABASE_URL)")
        return

    chunk = _sanitize_interval("chunk", settings.timescale_chunk_interval, "1 day")
    compress_after = _sanitize_interval("compress", settings.timescale_compress_after, "7 days")
    retention_raw = (settings.timescale_retention_interval or "").strip()
    retention = _sanitize_interval("retention", retention_raw, "") if retention_raw else ""

    engine = get_engine()
    async with engine.begin() as conn:
        if not await _table_exists(conn, "datasource_metric"):
            logger.warning("ensure_timescale: datasource_metric missing; skipping Timescale setup")
            return

        ext_ok = await _ensure_extension(conn)
        if not ext_ok:
            return

        setups = [
            ("datasource_metric", "collected_at", _set_compression_datasource),
            ("host_metric", "collected_at", _set_compression_host),
        ]

        for table, time_col, compression_setup in setups:
            if not await _table_exists(conn, table):
                logger.warning("ensure_timescale: table %s missing; skipping", table)
                continue
            await _ensure_composite_pk(conn, table, time_col)
            await _create_hypertable(conn, table, chunk)
            await compression_setup(conn)
            await _refresh_compression_policy(conn, table, compress_after)

        if retention:
            for table in ("datasource_metric", "host_metric"):
                if await _table_exists(conn, table) and await _is_hypertable(conn, table):
                    await _refresh_retention_policy(conn, table, retention)
        else:
            for table in ("datasource_metric", "host_metric"):
                await _clear_retention_if_disabled(conn, table)


async def downgrade() -> None:
    logger.warning("ensure_timescale: downgrade not supported automatically")


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("ensure_timescale migration completed")

    asyncio.run(main())
