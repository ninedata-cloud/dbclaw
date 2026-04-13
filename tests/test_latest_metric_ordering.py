import pytest

from backend.routers import datasources as datasources_router
from backend.routers import metrics as metrics_router


class _FakeScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return _FakeScalarResult(self._items)


class _FakeDB:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.last_statement = None

    async def execute(self, statement):
        self.last_statement = statement
        return _FakeResult(self.items)


@pytest.mark.asyncio
async def test_datasources_latest_metrics_prefers_latest_inserted_snapshot():
    fake_db = _FakeDB()

    await datasources_router.get_datasources_latest_metrics(db=fake_db)

    sql = str(fake_db.last_statement)
    assert "ORDER BY metric_snapshots.datasource_id, metric_snapshots.id DESC" in sql


@pytest.mark.asyncio
async def test_db_status_snapshot_query_prefers_latest_inserted_snapshot():
    fake_db = _FakeDB()

    await metrics_router._get_db_status_snapshots(fake_db, conn_id=1, limit=5)

    sql = str(fake_db.last_statement)
    assert "ORDER BY metric_snapshots.id DESC" in sql
