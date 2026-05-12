from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.routers import chat
from backend.routers.chat import _authenticate_websocket_session, _get_owned_session


class _Result:
    def __init__(self, row=None):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_owned_session_rejects_hidden_sessions_in_query():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(row=None))

    with pytest.raises(HTTPException) as exc_info:
        await _get_owned_session(db, 99, SimpleNamespace(id=2))

    assert exc_info.value.status_code == 404
    executed_stmt = db.execute.await_args.args[0]
    assert "diagnostic_session.is_hidden = false" in str(executed_stmt)


class _AsyncSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _WebSocket:
    cookies = {"dbclaw_session": "sid"}


@pytest.mark.api
@pytest.mark.asyncio
async def test_websocket_auth_rejects_hidden_sessions_in_query(mocker):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result(row=SimpleNamespace(id=2, is_active=True)),
        _Result(row=None),
    ])
    user_session = SimpleNamespace(user_id=2)
    mocker.patch("backend.routers.chat.SessionService.get_active_session", AsyncMock(return_value=user_session))
    mocker.patch("backend.routers.chat.SessionService.touch_session", AsyncMock())
    mocker.patch.object(chat, "async_session", lambda: _AsyncSessionContext(db))

    user, session = await _authenticate_websocket_session(_WebSocket(), 99)

    assert user is None
    assert session is None
    executed_stmt = db.execute.await_args_list[1].args[0]
    assert "diagnostic_session.is_hidden = false" in str(executed_stmt)
