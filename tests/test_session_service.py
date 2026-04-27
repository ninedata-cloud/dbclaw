from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.session_service import SessionService


@pytest.mark.unit
def test_as_utc_handles_naive_and_aware_datetime():
    naive = datetime(2026, 1, 1, 0, 0, 0)
    aware = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert SessionService._as_utc(naive).tzinfo == timezone.utc
    assert SessionService._as_utc(aware).tzinfo == timezone.utc


@pytest.mark.service
@pytest.mark.asyncio
async def test_create_session_truncates_user_agent_and_flushes(mocker):
    mocker.patch("backend.services.session_service.generate_session_id", return_value="raw-id")
    mocker.patch("backend.services.session_service.hash_session_id", return_value="hash-id")
    mocker.patch("backend.services.session_service.SessionService.build_expiry", return_value=datetime.now(timezone.utc))
    db = AsyncMock()
    db.add = MagicMock()

    raw = await SessionService.create_session(
        db,
        user_id=1,
        session_version=2,
        ip_address="127.0.0.1",
        user_agent="A" * 600,
    )

    assert raw == "raw-id"
    db.add.assert_called_once()
    db.flush.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_get_active_session_returns_none_when_expired(mocker):
    mocker.patch("backend.services.session_service.hash_session_id", return_value="h")
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(status="active", expires_at=past))
    )

    session = await SessionService.get_active_session(db, "raw")

    assert session is None
    db.commit.assert_awaited_once()


@pytest.mark.service
@pytest.mark.asyncio
async def test_touch_and_revoke_session_update_fields():
    db = AsyncMock()
    session = SimpleNamespace()
    await SessionService.touch_session(db, session)
    assert session.last_seen_at is not None
    assert session.expires_at is not None
    await SessionService.revoke_session(db, session, "logout")
    assert session.status == "revoked"
    assert session.revoked_reason == "logout"
    assert db.flush.await_count == 2
