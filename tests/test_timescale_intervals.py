"""Real asyncpg/TimescaleDB regression tests for issue #6.

Set DBCLAW_TEST_TIMESCALE_URL to a postgresql+asyncpg URL for a test server
with TimescaleDB installed and preloaded. Its user must be able to create
databases and the extension. Each case creates and drops its own database.
"""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from backend.migrations import ensure_timescale
from backend.models.datasource_metric import DatasourceMetric
from backend.models.host_metric import HostMetric


@pytest_asyncio.fixture
async def timescale_engine():
    raw_url = os.environ.get("DBCLAW_TEST_TIMESCALE_URL")
    if not raw_url:
        pytest.skip("Set DBCLAW_TEST_TIMESCALE_URL to run TimescaleDB integration tests")
    admin_url = make_url(raw_url)
    assert admin_url.drivername == "postgresql+asyncpg"
    database_name = f"dbclaw_issue6_{uuid4().hex}"
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    engine = create_async_engine(admin_url.set(database=database_name))
    created = False
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))
            created = True
        async with engine.begin() as conn:
            for table in (DatasourceMetric.__table__, HostMetric.__table__):
                await conn.run_sync(table.create)
        yield engine
    finally:
        await engine.dispose()
        try:
            if created:
                async with admin.connect() as conn:
                    await conn.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
        finally:
            await admin.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunk,compress_after,retention",
    [
        ("1 day", "7 days", ""),
        ("1.5 days", "7 days", "90 days"),
        ("1 day 2 hours", "7 days", "90 days"),
        ("01:30:00", "7 days", "90 days"),
        ("1 day", "1 month", "3 months"),
    ],
)
async def test_timescale_interval_configs_survive_repeated_startup(
    timescale_engine, monkeypatch, chunk, compress_after, retention
):
    settings = SimpleNamespace(
        database_url=timescale_engine.url.render_as_string(hide_password=False),
        timescale_enable=True,
        timescale_require_extension=True,
        timescale_chunk_interval=chunk,
        timescale_compress_after=compress_after,
        timescale_retention_interval=retention,
    )
    monkeypatch.setattr(ensure_timescale, "get_settings", lambda: settings)
    monkeypatch.setattr(ensure_timescale, "get_engine", lambda: timescale_engine)

    # Exercise both first-time hypertable creation and policy refresh on restart.
    await ensure_timescale.upgrade()
    await ensure_timescale.upgrade()

    async with timescale_engine.connect() as conn:
        for table in ("datasource_metric", "host_metric"):
            result = await conn.execute(
                text(
                    "SELECT time_interval = CAST(CAST(:chunk AS text) AS interval) "
                    "FROM timescaledb_information.dimensions "
                    "WHERE hypertable_schema = 'public' AND hypertable_name = :table"
                ),
                {"chunk": chunk, "table": table},
            )
            assert result.scalar_one() is True
            result = await conn.execute(
                text(
                    "SELECT proc_name, config FROM timescaledb_information.jobs "
                    "WHERE hypertable_schema = 'public' AND hypertable_name = :table "
                    "AND proc_name IN ('policy_compression', 'policy_retention')"
                ),
                {"table": table},
            )
            jobs = result.all()
            policies = {name: config for name, config in jobs}
            assert len(jobs) == (2 if retention else 1)
            expected = [("policy_compression", "compress_after", compress_after)]
            if retention:
                expected.append(("policy_retention", "drop_after", retention))
            for policy, key, value in expected:
                matches = await conn.scalar(
                    text(
                        "SELECT CAST(CAST(:actual AS text) AS interval) = "
                        "CAST(CAST(:expected AS text) AS interval)"
                    ),
                    {"actual": policies[policy][key], "expected": value},
                )
                assert matches is True
