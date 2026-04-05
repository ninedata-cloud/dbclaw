"""Test immediate metric collection after host operations"""
import asyncio
from sqlalchemy import select, desc
from backend.database import async_session
from backend.models.host import Host
from backend.models.host_metric import HostMetric
from backend.utils.encryption import encrypt_value


async def test_immediate_collection():
    """Test that metrics are collected immediately after host operations"""

    async with async_session() as db:
        # Find a test host
        result = await db.execute(select(Host).where(Host.host == '192.168.2.5'))
        host = result.scalar_one_or_none()

        if not host:
            print("Test host 192.168.2.5 not found")
            return

        print(f"Testing with host: {host.name} ({host.host})")
        print()

        # Get metrics before update
        result = await db.execute(
            select(HostMetric)
            .where(HostMetric.host_id == host.id)
            .order_by(desc(HostMetric.collected_at))
            .limit(1)
        )
        metric_before = result.scalar_one_or_none()

        if metric_before:
            print(f"Metrics before update:")
            print(f"  Time: {metric_before.collected_at}")
            print(f"  CPU: {metric_before.cpu_usage}%")
            print(f"  Memory: {metric_before.memory_usage}%")
            print(f"  Disk: {metric_before.disk_usage}%")
        else:
            print("No metrics before update")

        print()
        print("Simulating host update...")

        # Simulate an update by calling the collection function directly
        from backend.services.host_collector import _collect_host_metrics
        await _collect_host_metrics(db, host)
        await db.commit()

        # Get metrics after update
        result = await db.execute(
            select(HostMetric)
            .where(HostMetric.host_id == host.id)
            .order_by(desc(HostMetric.collected_at))
            .limit(1)
        )
        metric_after = result.scalar_one_or_none()

        print()
        print(f"Metrics after update:")
        print(f"  Time: {metric_after.collected_at}")
        print(f"  CPU: {metric_after.cpu_usage}%")
        print(f"  Memory: {metric_after.memory_usage}%")
        print(f"  Disk: {metric_after.disk_usage}%")

        # Verify that new metrics were collected
        if metric_before and metric_after:
            if metric_after.collected_at > metric_before.collected_at:
                print()
                print("✓ SUCCESS: New metrics were collected immediately!")
                time_diff = (metric_after.collected_at - metric_before.collected_at).total_seconds()
                print(f"  Time difference: {time_diff:.1f} seconds")
            else:
                print()
                print("✗ FAILED: No new metrics were collected")
        elif metric_after:
            print()
            print("✓ SUCCESS: Initial metrics were collected!")


if __name__ == "__main__":
    asyncio.run(test_immediate_collection())
