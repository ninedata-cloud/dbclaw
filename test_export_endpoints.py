"""Test export endpoints"""
import asyncio
from sqlalchemy import select
from backend.database import async_session
from backend.models.report import Report
from backend.models.datasource import Datasource


async def test_export():
    async with async_session() as db:
        # Find a completed report
        result = await db.execute(
            select(Report).where(Report.status == "completed").limit(1)
        )
        report = result.scalar_one_or_none()
        
        if not report:
            print("No completed reports found. Creating test report...")
            
            # Get first datasource
            ds_result = await db.execute(select(Datasource).limit(1))
            datasource = ds_result.scalar_one_or_none()
            
            if not datasource:
                print("No datasources found. Please create a datasource first.")
                return
            
            # Create test report
            test_report = Report(
                datasource_id=datasource.id,
                title=f"Test Inspection Report - {datasource.name}",
                report_type="inspection",
                status="completed",
                trigger_type="manual",
                trigger_reason="Test export functionality",
                content_md="""# Database Inspection Report

## Executive Summary
This is a test inspection report for export functionality.

## System Metrics
- CPU Usage: 45%
- Memory Usage: 60%
- Disk Usage: 75%

## Performance Analysis
The database is performing well with average query time of 50ms.

### Key Findings
1. No critical issues detected
2. Performance is within normal range
3. Resource utilization is healthy

## Recommendations
- Continue monitoring disk usage
- Review slow query log weekly
- Consider index optimization for frequently accessed tables

## Conclusion
System is healthy and operating normally.
""",
                generation_method="test"
            )
            db.add(test_report)
            await db.commit()
            await db.refresh(test_report)
            report = test_report
        
        print(f"\nTest Report Details:")
        print(f"  ID: {report.id}")
        print(f"  Title: {report.title}")
        print(f"  Status: {report.status}")
        print(f"  Has Markdown: {bool(report.content_md)}")
        print(f"\nExport URLs:")
        print(f"  Markdown: http://localhost:9939/api/inspections/reports/export/{report.id}/markdown")
        print(f"  PDF: http://localhost:9939/api/inspections/reports/export/{report.id}/pdf")
        print(f"\nYou can test these endpoints by:")
        print(f"  1. Start the server: python run.py")
        print(f"  2. Visit the inspection page and click export buttons")
        print(f"  3. Or use curl:")
        print(f"     curl -O http://localhost:9939/api/inspections/reports/export/{report.id}/markdown")
        print(f"     curl -O http://localhost:9939/api/inspections/reports/export/{report.id}/pdf")


if __name__ == "__main__":
    asyncio.run(test_export())
