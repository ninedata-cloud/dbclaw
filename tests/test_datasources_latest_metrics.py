from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from backend.routers.datasources import get_datasource_latest_metrics


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


async def test_get_datasource_latest_metrics_returns_lightweight_payload():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_RowsResult([
        (1, 12.5, 42, 7),
        (2, None, 0, None),
        (3, None, None, None),
    ]))

    result = await get_datasource_latest_metrics(db)

    assert result == {
        1: {"cpu_usage": 12.5, "qps": 42, "connections_active": 7},
        2: {"cpu_usage": None, "qps": 0, "connections_active": None},
        3: {"cpu_usage": None, "qps": None, "connections_active": None},
    }


async def test_get_datasource_latest_metrics_uses_lateral_latest_lookup():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_RowsResult([]))

    await get_datasource_latest_metrics(db)

    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))

    assert "JOIN LATERAL" in sql
    assert "LIMIT 1" in sql
    assert "ORDER BY datasource_metric.collected_at DESC, datasource_metric.id DESC" in sql
    assert "DISTINCT ON" not in sql
    assert "datasource.is_deleted = false" in sql
