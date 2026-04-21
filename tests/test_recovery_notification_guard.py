from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.alert_service import AlertService
from backend.services.notification_dispatcher import _process_recovery_notifications


@pytest.mark.asyncio
async def test_get_pending_recovery_notifications_requires_original_notification():
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    await AlertService.get_pending_recovery_notifications(db, minutes=60)

    stmt = db.execute.call_args[0][0]
    assert "alert_message.notified_at IS NOT NULL" in str(stmt)


@pytest.mark.asyncio
async def test_recovery_notification_skips_subscription_without_original_delivery():
    db = AsyncMock(spec=AsyncSession)
    alert = SimpleNamespace(id=101, datasource_id=9)
    subscription = SimpleNamespace(id=201)

    with patch(
        "backend.services.notification_dispatcher.AlertService.get_pending_recovery_notifications",
        new=AsyncMock(return_value=[alert]),
    ), patch(
        "backend.services.notification_dispatcher.AlertService.get_all_subscriptions",
        new=AsyncMock(return_value=[subscription]),
    ), patch(
        "backend.services.notification_dispatcher._is_datasource_silenced",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.services.notification_dispatcher.NotificationService.check_subscription_match",
        new=AsyncMock(return_value=True),
    ), patch(
        "backend.services.notification_dispatcher.AlertService.has_alert_notification_for_subscription",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.services.notification_dispatcher.AlertService.has_recovery_notification_for_subscription",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.services.notification_dispatcher._send_recovery_via_integration",
        new=AsyncMock(return_value=[]),
    ) as mock_send:
        await _process_recovery_notifications(db)

    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_notification_sends_only_after_original_delivery():
    db = AsyncMock(spec=AsyncSession)
    alert = SimpleNamespace(id=102, datasource_id=9, resolved_at=datetime(2026, 4, 6, 22, 13, 58))
    subscription = SimpleNamespace(id=202)
    mock_send = AsyncMock(return_value=[SimpleNamespace(status="sent")])

    with patch(
        "backend.services.notification_dispatcher.AlertService.get_pending_recovery_notifications",
        new=AsyncMock(return_value=[alert]),
    ), patch(
        "backend.services.notification_dispatcher.AlertService.get_all_subscriptions",
        new=AsyncMock(return_value=[subscription]),
    ), patch(
        "backend.services.notification_dispatcher._is_datasource_silenced",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.services.notification_dispatcher.NotificationService.check_subscription_match",
        new=AsyncMock(return_value=True),
    ), patch(
        "backend.services.notification_dispatcher.AlertService.has_alert_notification_for_subscription",
        new=AsyncMock(return_value=True),
    ), patch(
        "backend.services.notification_dispatcher.AlertService.has_recovery_notification_for_subscription",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.services.notification_dispatcher._send_recovery_via_integration",
        new=mock_send,
    ):
        await _process_recovery_notifications(db)

    mock_send.assert_awaited_once_with(db, alert, subscription)
