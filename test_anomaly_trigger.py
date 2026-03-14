"""
Test script for anomaly-triggered inspection
"""
import asyncio
from backend.database import get_db, init_db
from backend.services.threshold_checker import ThresholdChecker


async def test_threshold_checker():
    """Test the threshold checker logic"""
    print("Testing ThresholdChecker...\n")

    checker = ThresholdChecker()

    # Test case 1: CPU usage exceeds threshold
    print("Test 1: CPU usage exceeds threshold")
    threshold_rules = {
        "cpu_usage": {"threshold": 80, "duration": 5},  # 5 seconds for testing
        "memory_usage": {"threshold": 85, "duration": 5}
    }

    # First check - violation starts
    metrics1 = {"cpu_usage_percent": 95.5, "memory_usage_percent": 70}
    violations = checker.check_thresholds(1, metrics1, threshold_rules)
    print(f"  Check 1: CPU=95.5%, Memory=70% -> Violations: {len(violations)}")
    assert len(violations) == 0, "Should not trigger immediately"

    # Wait 6 seconds
    print("  Waiting 6 seconds...")
    await asyncio.sleep(6)

    # Second check - should trigger
    metrics2 = {"cpu_usage_percent": 96.0, "memory_usage_percent": 72}
    violations = checker.check_thresholds(1, metrics2, threshold_rules)
    print(f"  Check 2: CPU=96.0%, Memory=72% -> Violations: {len(violations)}")
    assert len(violations) == 1, "Should trigger after duration"
    assert violations[0]["metric_name"] == "cpu_usage"
    print(f"  ✓ Triggered: {violations[0]}")

    # Third check - should not trigger again (cooldown)
    violations = checker.check_thresholds(1, metrics2, threshold_rules)
    print(f"  Check 3: Same metrics -> Violations: {len(violations)}")
    assert len(violations) == 0, "Should not trigger again (cooldown)"
    print("  ✓ Cooldown working")

    # Test case 2: Metric returns to normal
    print("\nTest 2: Metric returns to normal")
    metrics3 = {"cpu_usage_percent": 75, "memory_usage_percent": 70}
    violations = checker.check_thresholds(1, metrics3, threshold_rules)
    print(f"  CPU=75%, Memory=70% -> Violations: {len(violations)}")
    assert len(violations) == 0, "Should not trigger when below threshold"
    print("  ✓ Violation cleared")

    # Test case 3: Multiple metrics exceed threshold
    print("\nTest 3: Multiple metrics exceed threshold")
    checker2 = ThresholdChecker()
    metrics4 = {"cpu_usage_percent": 95, "memory_usage_percent": 90}
    violations = checker2.check_thresholds(2, metrics4, threshold_rules)
    print(f"  Check 1: CPU=95%, Memory=90% -> Violations: {len(violations)}")

    await asyncio.sleep(6)

    violations = checker2.check_thresholds(2, metrics4, threshold_rules)
    print(f"  Check 2: After 6s -> Violations: {len(violations)}")
    assert len(violations) == 2, "Should trigger both metrics"
    print(f"  ✓ Triggered: {[v['metric_name'] for v in violations]}")

    # Test case 4: Metric name mapping
    print("\nTest 4: Metric name mapping")
    checker3 = ThresholdChecker()
    # Use alternative metric names
    metrics5 = {"cpu.usage_percent": 95, "mem_percent": 90}
    violations = checker3.check_thresholds(3, metrics5, threshold_rules)
    print(f"  Check 1: cpu.usage_percent=95%, mem_percent=90% -> Violations: {len(violations)}")

    await asyncio.sleep(6)

    violations = checker3.check_thresholds(3, metrics5, threshold_rules)
    print(f"  Check 2: After 6s -> Violations: {len(violations)}")
    assert len(violations) == 2, "Should handle alternative metric names"
    print(f"  ✓ Triggered with alternative names: {[v['metric_name'] for v in violations]}")

    print("\n" + "="*60)
    print("✓ All threshold checker tests passed!")
    print("="*60)


async def test_config_api():
    """Test inspection config API"""
    print("\nTesting Inspection Config API...\n")

    await init_db()

    async for db in get_db():
        from backend.models.inspection_config import InspectionConfig
        from sqlalchemy import select

        # Get or create config for datasource 1
        result = await db.execute(
            select(InspectionConfig).where(InspectionConfig.datasource_id == 1)
        )
        config = result.scalar_one_or_none()

        if not config:
            print("Creating default config for datasource 1...")
            config = InspectionConfig(
                datasource_id=1,
                enabled=True,
                schedule_interval=86400,
                use_ai_analysis=True,
                threshold_rules={
                    "cpu_usage": {"threshold": 80, "duration": 60},
                    "memory_usage": {"threshold": 85, "duration": 60},
                    "disk_usage": {"threshold": 80, "duration": 300}
                }
            )
            db.add(config)
            await db.commit()
            await db.refresh(config)

        print(f"Config for datasource {config.datasource_id}:")
        print(f"  Enabled: {config.enabled}")
        print(f"  Schedule interval: {config.schedule_interval}s")
        print(f"  Threshold rules: {config.threshold_rules}")
        print("  ✓ Config loaded successfully")

        break


if __name__ == "__main__":
    print("="*60)
    print("Anomaly-Triggered Inspection Test Suite")
    print("="*60 + "\n")

    asyncio.run(test_threshold_checker())
    asyncio.run(test_config_api())

    print("\n" + "="*60)
    print("✓ All tests completed successfully!")
    print("="*60)
