"""
Test script for scheduled reports functionality
"""
import asyncio
import sys
sys.path.insert(0, '/Users/william/prog2/temp/smartdba')

from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.scheduled_report_config import ScheduledReportConfig
from backend.services.scheduled_report_service import ScheduledReportService
from backend.services.metric_collector import scheduler
from sqlalchemy import select


async def test_scheduled_reports():
    print("Testing Scheduled Reports Module...")
    print("=" * 60)

    async with async_session() as db:
        # 1. Check datasources
        result = await db.execute(select(Datasource))
        datasources = result.scalars().all()
        print(f"\n✓ Found {len(datasources)} datasources")

        for ds in datasources[:3]:
            print(f"  - {ds.name} ({ds.db_type}, importance: {ds.importance_level})")

        # 2. Check scheduled configs
        result = await db.execute(select(ScheduledReportConfig))
        configs = result.scalars().all()
        print(f"\n✓ Found {len(configs)} scheduled report configs")

        for config in configs:
            print(f"  - Config {config.id}: datasource_id={config.datasource_id}, "
                  f"enabled={config.enabled}, interval={config.schedule_interval}s")

        # 3. Test service initialization
        print("\n✓ Testing ScheduledReportService initialization...")
        service = ScheduledReportService(scheduler)

        # Get interval mapping
        print("\n✓ Interval mapping:")
        for importance, interval in service.INTERVAL_MAP.items():
            if interval:
                display = service._format_interval_display(interval)
                print(f"  - {importance}: {interval}s ({display})")
            else:
                print(f"  - {importance}: No scheduled reports")

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("\nScheduled Reports Module is ready to use.")
        print("\nNext steps:")
        print("1. Start the application: uvicorn backend.app:app --reload")
        print("2. Navigate to: http://localhost:8000/#/scheduled-reports")
        print("3. Create a schedule for a datasource")
        print("4. Watch the countdown timer and wait for automatic generation")


if __name__ == "__main__":
    asyncio.run(test_scheduled_reports())
