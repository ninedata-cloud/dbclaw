import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_check_network_success():
    """ping 返回 0 时应返回 True"""
    from backend.services.network_probe import check_network

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await check_network("127.0.0.1")
    assert result is True


@pytest.mark.asyncio
async def test_check_network_failure():
    """ping 返回非 0 时应返回 False"""
    from backend.services.network_probe import check_network

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock(return_value=1)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await check_network("192.0.2.1")
    assert result is False


@pytest.mark.asyncio
async def test_check_network_timeout():
    """超时应返回 False"""
    from backend.services.network_probe import check_network

    mock_proc = MagicMock()
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await check_network("192.0.2.1")
    assert result is False


@pytest.mark.asyncio
async def test_check_network_exception():
    """创建进程异常应返回 False"""
    from backend.services.network_probe import check_network

    with patch("asyncio.create_subprocess_exec", side_effect=OSError("no ping")):
        result = await check_network("127.0.0.1")
    assert result is False
