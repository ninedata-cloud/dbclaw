"""
Test auto-resolve alerts functionality
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.metric_collector import (
    _auto_resolve_recovered_alerts,
    _auto_resolve_connection_alerts
)
from backend.models.alert_message import AlertMessage


async def test_auto_resolve_recovered_alerts():
    """Test that alerts are auto-resolved when metrics recover"""
    print("\n=== Testing Auto-Resolve Recovered Alerts ===")

    # Mock database session
    db = AsyncMock(spec=AsyncSession)

    # Create mock active alerts
    alert1 = MagicMock(spec=AlertMessage)
    alert1.id = 1
    alert1.metric_name = "cpu_usage"
    alert1.status = "active"

    alert2 = MagicMock(spec=AlertMessage)
    alert2.id = 2
    alert2.metric_name = "memory_usage"
    alert2.status = "acknowledged"

    alert3 = MagicMock(spec=AlertMessage)
    alert3.id = 3
    alert3.metric_name = "disk_usage"
    alert3.status = "active"

    # Mock database query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [alert1, alert2, alert3]
    db.execute.return_value = mock_result

    # Current metrics (cpu and memory recovered, disk still high)
    metrics = {
        "cpu_usage": 60.0,  # Below threshold
        "memory_usage": 70.0,  # Below threshold
        "disk_usage": 95.0,  # Still above threshold
    }

    # Threshold rules
    threshold_rules = [
        {"metric_name": "cpu_usage", "threshold": 80.0},
        {"metric_name": "memory_usage", "threshold": 85.0},
        {"metric_name": "disk_usage", "threshold": 90.0},
    ]

    # Current violations (only disk_usage)
    current_violations = [
        {"metric_name": "disk_usage", "current_value": 95.0}
    ]

    # Mock AlertService.resolve_alert
    with patch('backend.services.alert_service.AlertService.resolve_alert') as mock_resolve:
        mock_resolve.return_value = AsyncMock()

        # Call the function
        await _auto_resolve_recovered_alerts(
            db=db,
            datasource_id=1,
            metrics=metrics,
            threshold_rules=threshold_rules,
            current_violations=current_violations
        )

        # Verify that only cpu_usage and memory_usage alerts were resolved
        assert mock_resolve.call_count == 2, f"Expected 2 resolve calls, got {mock_resolve.call_count}"

        # Check which alerts were resolved
        resolved_alert_ids = [call[0][1] for call in mock_resolve.call_args_list]
        assert 1 in resolved_alert_ids, "cpu_usage alert should be resolved"
        assert 2 in resolved_alert_ids, "memory_usage alert should be resolved"
        assert 3 not in resolved_alert_ids, "disk_usage alert should NOT be resolved (still violating)"

        print("✓ Auto-resolve recovered alerts works correctly")
        print(f"  - Resolved alerts: {resolved_alert_ids}")
        print(f"  - Skipped alert 3 (disk_usage still violating)")


async def test_auto_resolve_connection_alerts():
    """Test that connection failure alerts are auto-resolved when connection is restored"""
    print("\n=== Testing Auto-Resolve Connection Alerts ===")

    # Mock database session
    db = AsyncMock(spec=AsyncSession)

    # Create mock connection failure alerts
    alert1 = MagicMock(spec=AlertMessage)
    alert1.id = 10
    alert1.status = "active"

    alert2 = MagicMock(spec=AlertMessage)
    alert2.id = 11
    alert2.status = "acknowledged"

    # Mock database query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [alert1, alert2]
    db.execute.return_value = mock_result

    # Mock AlertService.resolve_alert
    with patch('backend.services.alert_service.AlertService.resolve_alert') as mock_resolve:
        mock_resolve.return_value = AsyncMock()

        # Call the function
        await _auto_resolve_connection_alerts(db=db, datasource_id=1)

        # Verify that both connection alerts were resolved
        assert mock_resolve.call_count == 2, f"Expected 2 resolve calls, got {mock_resolve.call_count}"

        # Check which alerts were resolved
        resolved_alert_ids = [call[0][1] for call in mock_resolve.call_args_list]
        assert 10 in resolved_alert_ids, "Connection alert 10 should be resolved"
        assert 11 in resolved_alert_ids, "Connection alert 11 should be resolved"

        print("✓ Auto-resolve connection alerts works correctly")
        print(f"  - Resolved connection alerts: {resolved_alert_ids}")


async def test_no_alerts_to_resolve():
    """Test that function handles case with no active alerts gracefully"""
    print("\n=== Testing No Alerts to Resolve ===")

    # Mock database session
    db = AsyncMock(spec=AsyncSession)

    # Mock empty query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    metrics = {"cpu_usage": 60.0}
    threshold_rules = [{"metric_name": "cpu_usage", "threshold": 80.0}]
    current_violations = []

    # Mock AlertService.resolve_alert
    with patch('backend.services.alert_service.AlertService.resolve_alert') as mock_resolve:
        # Call the function
        await _auto_resolve_recovered_alerts(
            db=db,
            datasource_id=1,
            metrics=metrics,
            threshold_rules=threshold_rules,
            current_violations=current_violations
        )

        # Verify no resolve calls were made
        assert mock_resolve.call_count == 0, "No resolve calls should be made when no alerts exist"
        print("✓ Handles no alerts case correctly")


async def main():
    """Run all tests"""
    print("Starting Auto-Resolve Alerts Tests...")

    try:
        await test_auto_resolve_recovered_alerts()
        await test_auto_resolve_connection_alerts()
        await test_no_alerts_to_resolve()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
