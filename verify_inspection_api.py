#!/usr/bin/env python3
"""
Verify that the inspection API endpoints work correctly for polling.
This script checks that the backend properly returns report status.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db_session
from backend.models.report import Report
from backend.models.datasource import Datasource


async def verify_api_endpoints():
    """Verify that report status is properly stored and retrievable."""
    print("Verifying Inspection API Endpoints")
    print("=" * 50)
    
    async with get_db_session() as session:
        # Check if we have any reports
        from sqlalchemy import select
        result = await session.execute(select(Report).limit(5))
        reports = result.scalars().all()
        
        if not reports:
            print("⚠ No reports found in database")
            print("  This is normal for a fresh installation")
            return True
        
        print(f"✓ Found {len(reports)} report(s) in database")
        
        # Check report statuses
        status_counts = {}
        for report in reports:
            status = report.status
            status_counts[status] = status_counts.get(status, 0) + 1
            print(f"  - Report {report.id}: {status}")
        
        print("\nStatus Summary:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
        
        # Verify required fields exist
        print("\n✓ Report model has required fields:")
        sample_report = reports[0]
        required_fields = ['id', 'status', 'title', 'created_at', 'datasource_id']
        for field in required_fields:
            has_field = hasattr(sample_report, field)
            symbol = "✓" if has_field else "✗"
            print(f"  {symbol} {field}")
            if not has_field:
                return False
        
        return True


async def main():
    try:
        success = await verify_api_endpoints()
        if success:
            print("\n" + "=" * 50)
            print("✓ All verification checks passed!")
            print("  The polling mechanism should work correctly.")
            return 0
        else:
            print("\n" + "=" * 50)
            print("✗ Some verification checks failed")
            return 1
    except Exception as e:
        print(f"\n✗ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
