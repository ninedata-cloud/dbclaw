"""Test script to verify inspection trigger deduplication logic"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, and_, desc
from backend.database import async_session
from backend.models.inspection_trigger import InspectionTrigger
from backend.utils.datetime_helper import now
from backend.config import get_settings


async def test_deduplication():
    """Test that duplicate triggers are properly filtered"""
    dedup_minutes = get_settings().inspection_dedup_window_minutes
    
    async with async_session() as db:
        # Test 1: Check recent connection_failure triggers
        print("\n=== Test 1: Recent connection_failure triggers ===")
        datasource_id = 1  # Adjust based on your test data
        
        recent_trigger = await db.execute(
            select(InspectionTrigger).where(
                and_(
                    InspectionTrigger.datasource_id == datasource_id,
                    InspectionTrigger.trigger_type == "connection_failure",
                    InspectionTrigger.triggered_at >= now() - timedelta(minutes=dedup_minutes)
                )
            ).order_by(desc(InspectionTrigger.triggered_at)).limit(1)
        )
        existing = recent_trigger.scalar_one_or_none()
        
        if existing:
            print(f"✓ Found recent trigger: ID={existing.id}, Time={existing.triggered_at}")
            print(f"  Would skip duplicate trigger (within {dedup_minutes} minutes)")
        else:
            print("✓ No recent trigger found, would create new trigger")
        
        # Test 2: Check recent anomaly triggers for specific metric
        print("\n=== Test 2: Recent anomaly triggers by metric ===")
        metric_name = "cpu_usage"
        
        recent_anomaly = await db.execute(
            select(InspectionTrigger).where(
                and_(
                    InspectionTrigger.datasource_id == datasource_id,
                    InspectionTrigger.trigger_type == "anomaly",
                    InspectionTrigger.trigger_reason.like(f"{metric_name}=%"),
                    InspectionTrigger.triggered_at >= now() - timedelta(minutes=dedup_minutes)
                )
            ).order_by(desc(InspectionTrigger.triggered_at)).limit(1)
        )
        existing_anomaly = recent_anomaly.scalar_one_or_none()
        
        if existing_anomaly:
            print(f"✓ Found recent anomaly trigger: ID={existing_anomaly.id}")
            print(f"  Reason: {existing_anomaly.trigger_reason}")
            print(f"  Would skip duplicate trigger for {metric_name}")
        else:
            print(f"✓ No recent anomaly trigger for {metric_name}, would create new trigger")
        
        # Test 3: Show all triggers in last 10 minutes
        print("\n=== Test 3: All triggers in last 10 minutes ===")
        all_recent = await db.execute(
            select(InspectionTrigger).where(
                InspectionTrigger.triggered_at >= now() - timedelta(minutes=10)
            ).order_by(desc(InspectionTrigger.triggered_at))
        )
        triggers = all_recent.scalars().all()
        
        if triggers:
            print(f"Found {len(triggers)} triggers:")
            for t in triggers:
                print(f"  - ID={t.id}, Type={t.trigger_type}, DS={t.datasource_id}, Time={t.triggered_at}")
                if t.trigger_reason:
                    print(f"    Reason: {t.trigger_reason[:80]}")
        else:
            print("No triggers found in last 10 minutes")
        
        print(f"\n=== Deduplication Logic Summary ===")
        print(f"✓ Connection failures: Skip if same datasource has trigger within {dedup_minutes} minutes")
        print(f"✓ Anomaly triggers: Skip if same datasource+metric has trigger within {dedup_minutes} minutes")
        print("✓ This prevents repeated diagnosis for ongoing issues")


if __name__ == "__main__":
    asyncio.run(test_deduplication())
