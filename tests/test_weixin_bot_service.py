import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services import weixin_bot_service
from backend.services.weixin_bot_service import (
    WeixinBotService,
    _SuppressWeixinPollingHttpxFilter,
    _configure_weixin_polling_logging,
)


@pytest.mark.asyncio
async def test_poll_once_without_messages_does_not_emit_info_log(monkeypatch):
    binding = SimpleNamespace(
        params={
            "api_baseurl": "https://ilinkai.weixin.qq.com",
            "bot_token": "plain-token",
            "login_status": "confirmed",
            "receive_timeout_seconds": 40,
            "get_updates_buf": "cursor-1",
        }
    )
    db = AsyncMock()
    info_mock = Mock()

    monkeypatch.setattr(
        weixin_bot_service.weixin_service,
        "get_updates",
        AsyncMock(return_value={"msgs": [], "get_updates_buf": "cursor-1"}),
    )
    monkeypatch.setattr(weixin_bot_service.logger, "info", info_mock)
    monkeypatch.setattr(weixin_bot_service, "_MESSAGE_QUEUE", asyncio.Queue())

    await WeixinBotService.poll_once(db, binding)

    info_mock.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_poll_once_with_messages_emits_summary_info(monkeypatch):
    binding = SimpleNamespace(
        params={
            "api_baseurl": "https://ilinkai.weixin.qq.com",
            "bot_token": "plain-token",
            "login_status": "confirmed",
            "receive_timeout_seconds": 40,
            "get_updates_buf": "cursor-1",
        }
    )
    db = AsyncMock()
    info_mock = Mock()
    queue = asyncio.Queue()

    monkeypatch.setattr(
        weixin_bot_service.weixin_service,
        "get_updates",
        AsyncMock(
            return_value={
                "msgs": [{"message_id": "m1"}, {"message_id": "m2"}],
                "get_updates_buf": "cursor-1",
            }
        ),
    )
    monkeypatch.setattr(weixin_bot_service.logger, "info", info_mock)
    monkeypatch.setattr(weixin_bot_service, "_MESSAGE_QUEUE", queue)

    await WeixinBotService.poll_once(db, binding)

    info_mock.assert_called_once()
    assert "收到 2 条新消息" in info_mock.call_args.args[0]
    assert queue.qsize() == 2


def test_httpx_weixin_polling_filter_suppresses_only_info_getupdates_logs():
    log_filter = _SuppressWeixinPollingHttpxFilter()

    suppressed = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: POST https://ilinkai.weixin.qq.com/ilink/bot/getupdates "HTTP/1.1 200 OK"',
        args=(),
        exc_info=None,
    )
    kept_send = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: POST https://ilinkai.weixin.qq.com/ilink/bot/sendmessage "HTTP/1.1 200 OK"',
        args=(),
        exc_info=None,
    )
    kept_error = logging.LogRecord(
        name="httpx",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: POST https://ilinkai.weixin.qq.com/ilink/bot/getupdates "HTTP/1.1 500 Internal Server Error"',
        args=(),
        exc_info=None,
    )

    assert log_filter.filter(suppressed) is False
    assert log_filter.filter(kept_send) is True
    assert log_filter.filter(kept_error) is True


def test_configure_weixin_polling_logging_adds_filter_only_once():
    httpx_logger = logging.getLogger("httpx")
    original_filters = list(httpx_logger.filters)

    try:
        for log_filter in list(httpx_logger.filters):
            if isinstance(log_filter, _SuppressWeixinPollingHttpxFilter):
                httpx_logger.removeFilter(log_filter)

        _configure_weixin_polling_logging()
        _configure_weixin_polling_logging()

        assert sum(
            isinstance(log_filter, _SuppressWeixinPollingHttpxFilter)
            for log_filter in httpx_logger.filters
        ) == 1
    finally:
        httpx_logger.filters = original_filters
