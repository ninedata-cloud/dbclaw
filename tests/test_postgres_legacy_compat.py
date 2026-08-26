from datetime import datetime, timezone

import pytest

from backend.services.metric_collector import _probe_connection_after_collection_error
from backend.services.postgres_service import PostgreSQLConnector


PG94_ACTIVITY_COLUMNS = {
    "datname",
    "pid",
    "usename",
    "client_addr",
    "query_start",
    "xact_start",
    "state",
    "waiting",
    "query",
}


class FakePostgresConnection:
    def __init__(self, columns, process_rows=None):
        self.columns = columns
        self.process_rows = process_rows or []
        self.queries = []
        self.closed = False

    async def fetch(self, query, *args):
        self.queries.append(query)
        if "pg_catalog.pg_attribute" in query:
            return [{"attname": column} for column in self.columns]
        return self.process_rows

    async def fetchrow(self, query, *args):
        self.queries.append(query)
        if "FROM pg_stat_database" in query:
            return {
                "numbackends": 3,
                "xact_commit": 10,
                "xact_rollback": 1,
                "blks_read": 20,
                "blks_hit": 80,
                "tup_returned": 100,
                "tup_fetched": 90,
                "tup_inserted": 4,
                "tup_updated": 3,
                "tup_deleted": 2,
                "conflicts": 0,
                "deadlocks": 0,
            }
        if "count(*) as total" in query:
            return {"total": 3, "active": 1, "idle": 2, "waiting": 1}
        if "pg_database_size" in query:
            return {"db_size": 1024}
        if "pg_postmaster_start_time" in query:
            return {"start_time": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        if "max_connections" in query:
            return {"max_conn": 100}
        if "max(now() - xact_start)" in query:
            return {"seconds": 12}
        raise AssertionError(f"Unexpected query: {query}")

    async def close(self):
        self.closed = True


@pytest.mark.service
@pytest.mark.asyncio
async def test_pg94_greenplum_status_uses_waiting_column(mocker):
    connection = FakePostgresConnection(PG94_ACTIVITY_COLUMNS)
    connector = PostgreSQLConnector("db", 5432, "monitor", "secret", "postgres")
    mocker.patch.object(connector, "_connect", return_value=connection)

    status = await connector.get_status()

    activity_query = next(query for query in connection.queries if "count(*) as total" in query)
    assert "waiting = true" in activity_query
    assert "wait_event_type" not in activity_query
    assert status["connections_waiting"] == 1
    assert status["lock_waiting"] == 1
    assert connection.closed


@pytest.mark.service
@pytest.mark.asyncio
async def test_pg94_greenplum_process_list_normalizes_lock_wait(mocker):
    expected_rows = [{"pid": 42, "wait_event_type": "Lock", "wait_event": "Lock", "query": "select 1"}]
    connection = FakePostgresConnection(PG94_ACTIVITY_COLUMNS, expected_rows)
    connector = PostgreSQLConnector("db", 5432, "monitor", "secret", "postgres")
    mocker.patch.object(connector, "_connect", return_value=connection)

    rows = await connector.get_process_list()

    process_query = connection.queries[-1]
    assert "CASE WHEN waiting THEN 'Lock' ELSE NULL END AS wait_event_type" in process_query
    assert "query AS query" in process_query
    assert "query_start, wait_event_type" not in process_query
    assert rows == expected_rows
    assert connection.closed


@pytest.mark.service
@pytest.mark.asyncio
async def test_metric_query_error_is_not_classified_as_connection_failure():
    class ReachableConnector:
        async def test_connection(self):
            return "PostgreSQL 9.4 (Greenplum)"

    failed, detail = await _probe_connection_after_collection_error(
        ReachableConnector(),
        RuntimeError('column "wait_event_type" does not exist'),
    )

    assert failed is False
    assert detail == 'column "wait_event_type" does not exist'


@pytest.mark.service
@pytest.mark.asyncio
async def test_failed_probe_is_classified_as_connection_failure():
    class UnreachableConnector:
        async def test_connection(self):
            raise OSError("connection refused")

    failed, detail = await _probe_connection_after_collection_error(
        UnreachableConnector(),
        RuntimeError("metric query failed"),
    )

    assert failed is True
    assert detail == "connection refused"
