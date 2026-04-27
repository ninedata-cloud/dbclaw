from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from jose import JWTError

from backend.services.public_share_service import PublicShareService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_external_base_url_strips_trailing_slash(mocker):
    mocker.patch("backend.services.public_share_service.get_config", AsyncMock(return_value="https://a.com/"))
    value = await PublicShareService.get_external_base_url(AsyncMock())
    assert value == "https://a.com"


@pytest.mark.unit
def test_create_share_tokens_delegate_to_security(mocker):
    create_token = mocker.patch(
        "backend.services.public_share_service.create_public_share_token",
        return_value="token-x",
    )
    assert PublicShareService.create_alert_share_token(1, 30) == "token-x"
    assert PublicShareService.create_report_share_token(2, 30) == "token-x"
    assert create_token.call_count == 2


@pytest.mark.unit
def test_verify_alert_share_token_raises_401_on_jwt_error(mocker):
    mocker.patch(
        "backend.services.public_share_service.decode_public_share_token",
        side_effect=JWTError("bad"),
    )
    with pytest.raises(HTTPException) as exc:
        PublicShareService.verify_alert_share_token("x", 1)
    assert exc.value.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_alert_or_404_raises_when_missing():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await PublicShareService.get_alert_or_404(db, 1)
    assert exc.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_report_or_404_returns_entity(mocker):
    report = SimpleNamespace(id=7)
    mocker.patch(
        "backend.services.public_share_service.get_alive_by_id",
        AsyncMock(return_value=report),
    )
    got = await PublicShareService.get_report_or_404(AsyncMock(), 7)
    assert got.id == 7
