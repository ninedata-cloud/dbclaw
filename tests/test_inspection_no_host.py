"""Test inspection report generation with datasource that has no host"""
import asyncio
import sys
from sqlalchemy import select
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.inspection_trigger import InspectionTrigger
from backend.services.inspection_service import InspectionService


async def test_inspection_report_no_host():
    """Test inspection report generation with a datasource that has no host"""
    async with async_session() as db:
        # Find a datasource without host_id
        result = await db.execute(
            select(Datasource).where(Datasource.host_id == None)
        )
        datasource = result.scalars().first()

        if not datasource:
            print("❌ No datasource without host_id found")
            return False

        print(f"✓ Found datasource {datasource.id} ({datasource.name}) without host_id")

        # Create inspection service
        from backend.database import async_session as session_factory
        inspection_service = InspectionService(session_factory)

        # Trigger manual inspection
        print(f"\nTriggering manual inspection for datasource {datasource.id}...")
        trigger_id = await inspection_service.trigger_inspection(
            db=db,
            datasource_id=datasource.id,
            trigger_type="manual",
            reason="Test inspection for datasource without host"
        )

        print(f"✓ Created inspection trigger {trigger_id}")

        # Wait a bit for report generation
        await asyncio.sleep(5)

        # Check the trigger status
        result = await db.execute(
            select(InspectionTrigger).where(InspectionTrigger.id == trigger_id)
        )
        trigger = result.scalar_one()

        print(f"\nTrigger status:")
        print(f"  processed: {trigger.processed}")
        print(f"  report_id: {trigger.report_id}")

        if trigger.report_id:
            from backend.models.report import Report
            result = await db.execute(
                select(Report).where(Report.id == trigger.report_id)
            )
            report = result.scalar_one()

            print(f"\nReport status:")
            print(f"  status: {report.status}")
            print(f"  generation_method: {report.generation_method}")

            if report.content_md:
                print(f"  content_md length: {len(report.content_md)} chars")
                print(f"\nFirst 500 chars of report:")
                print("-" * 60)
                print(report.content_md[:500])
                print("-" * 60)

                # Check if report mentions the no-host issue gracefully
                if "未配置主机" in report.content_md or "no_host_configured" in report.content_md:
                    print("\n✅ Report correctly mentions missing host configuration")
                else:
                    print("\n⚠️  Report doesn't mention missing host (AI may have skipped OS metrics)")

            if report.status == "completed":
                print("\n✅ Test PASSED: Report generated successfully despite missing host")
                return True
            else:
                print(f"\n❌ Test FAILED: Report status is {report.status}")
                if report.error_message:
                    print(f"Error: {report.error_message}")
                return False
        else:
            print("\n❌ Test FAILED: No report was generated")
            return False


async def main():
    print("=" * 60)
    print("Testing inspection report with datasource without host")
    print("=" * 60)

    test_passed = await test_inspection_report_no_host()

    print("\n" + "=" * 60)
    if test_passed:
        print("🎉 Test PASSED!")
        return 0
    else:
        print("❌ Test FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
