from types import SimpleNamespace

import pytest

from backend.services import integration_scheduler


def _fake_connector(status_payload: dict, *, close_error: BaseException | None = None):
    """Avoid AsyncMock on async connector methods (teardown RuntimeWarning on Py3.13)."""
    close_calls: list[None] = []

    async def get_status():
        return status_payload

    async def close():
        close_calls.append(None)
        if close_error is not None:
            raise close_error

    return SimpleNamespace(get_status=get_status, close=close), close_calls


@pytest.mark.unit
def test_stop_integration_scheduler_shutdowns_and_clears(mocker):
    fake_scheduler = SimpleNamespace(shutdown=mocker.Mock())
    integration_scheduler.scheduler = fake_scheduler
    integration_scheduler.stop_integration_scheduler()
    fake_scheduler.shutdown.assert_called_once()
    assert integration_scheduler.scheduler is None


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_direct_metrics_supplement_extracts_expected_fields(mocker):
    connector, close_calls = _fake_connector(
        {
            "max_connections": 100,
            "uptime": 3600,
            "cache_hit_rate": 99.9,
            "other": "ignore",
        }
    )
    mocker.patch("backend.utils.encryption.decrypt_value", return_value="pwd")
    mocker.patch("backend.services.db_connector.get_connector", return_value=connector)
    datasource = SimpleNamespace(
        password_encrypted="enc",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        username="root",
        database="test",
        extra_params={},
    )

    data = await integration_scheduler._collect_direct_metrics_supplement(datasource)

    assert data["max_connections"] == 100
    assert data["uptime"] == 3600
    assert data["cache_hit_rate"] == 99.9
    assert len(close_calls) == 1


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_direct_metrics_supplement_includes_buffer_pool_hit_rate(mocker):
    connector, _ = _fake_connector({"buffer_pool_hit_rate": 98.5, "max_connections": 50})
    mocker.patch("backend.utils.encryption.decrypt_value", return_value="pwd")
    mocker.patch("backend.services.db_connector.get_connector", return_value=connector)
    datasource = SimpleNamespace(
        password_encrypted="enc",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        username="root",
        database="test",
        extra_params={},
    )

    data = await integration_scheduler._collect_direct_metrics_supplement(datasource)

    assert data["buffer_pool_hit_rate"] == 98.5
    assert data["max_connections"] == 50


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_direct_metrics_supplement_returns_empty_on_connector_error(mocker):
    mocker.patch("backend.utils.encryption.decrypt_value", return_value="pwd")
    mocker.patch("backend.services.db_connector.get_connector", side_effect=RuntimeError("boom"))
    datasource = SimpleNamespace(
        id=99,
        password_encrypted="enc",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        username="root",
        database="test",
        extra_params={},
    )

    data = await integration_scheduler._collect_direct_metrics_supplement(datasource)

    assert data == {}


@pytest.mark.service
@pytest.mark.asyncio
async def test_collect_direct_metrics_supplement_swallows_close_errors(mocker):
    connector, close_calls = _fake_connector({}, close_error=RuntimeError("close failed"))
    mocker.patch("backend.utils.encryption.decrypt_value", return_value="pwd")
    mocker.patch("backend.services.db_connector.get_connector", return_value=connector)
    datasource = SimpleNamespace(
        password_encrypted="enc",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        username="root",
        database="test",
        extra_params={},
    )

    data = await integration_scheduler._collect_direct_metrics_supplement(datasource)

    assert data == {}
    assert len(close_calls) == 1
