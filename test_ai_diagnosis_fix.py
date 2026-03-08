"""
测试 AI 诊断修复
验证异常检测后能够正确触发 AI 诊断
"""
import asyncio
import sys
from sqlalchemy import select

# Add backend to path
sys.path.insert(0, 'backend')

from backend.database import async_session
from backend.models.anomaly import Anomaly
from backend.models.datasource import Datasource
from backend.services.anomaly_detector import AnomalyDetector


async def test_diagnosis_trigger():
    """测试诊断触发机制"""
    print("🧪 Testing AI Diagnosis Fix...")
    print("=" * 60)

    async with async_session() as db:
        # 1. 查找最近的异常
        result = await db.execute(
            select(Anomaly)
            .order_by(Anomaly.detected_at.desc())
            .limit(5)
        )
        anomalies = result.scalars().all()

        if not anomalies:
            print("❌ No anomalies found in database")
            return

        print(f"✅ Found {len(anomalies)} recent anomalies\n")

        # 2. 检查诊断状态
        diagnosed_count = 0
        pending_count = 0

        for anomaly in anomalies:
            status = "✅ Diagnosed" if anomaly.ai_diagnosis else "⏳ Pending"
            print(f"Anomaly #{anomaly.id}:")
            print(f"  - Datasource: {anomaly.datasource_id}")
            print(f"  - Severity: {anomaly.severity}")
            print(f"  - Type: {anomaly.anomaly_type}")
            print(f"  - Status: {status}")

            if anomaly.ai_diagnosis:
                diagnosed_count += 1
                print(f"  - Diagnosis length: {len(anomaly.ai_diagnosis)} chars")
                if anomaly.root_cause:
                    print(f"  - Root cause: {anomaly.root_cause[:100]}...")
            else:
                pending_count += 1
            print()

        print("=" * 60)
        print(f"Summary:")
        print(f"  - Diagnosed: {diagnosed_count}")
        print(f"  - Pending: {pending_count}")
        print()

        # 3. 检查数据源重要性级别
        result = await db.execute(
            select(Datasource).where(Datasource.is_active == True)
        )
        datasources = result.scalars().all()

        critical_count = sum(1 for ds in datasources if ds.importance_level == 'core')
        important_count = sum(1 for ds in datasources if ds.importance_level == 'production')

        print(f"Active Datasources:")
        print(f"  - CRITICAL (core): {critical_count}")
        print(f"  - IMPORTANT (production): {important_count}")
        print(f"  - Total: {len(datasources)}")
        print()

        if pending_count > 0 and (critical_count > 0 or important_count > 0):
            print("⚠️  Note: Pending diagnoses found for CRITICAL/IMPORTANT datasources")
            print("   This may indicate:")
            print("   1. Anomalies were just detected (diagnosis in progress)")
            print("   2. Previous diagnosis tasks failed (check logs)")
            print("   3. Datasource importance level is NORMAL (diagnosis not triggered)")
            print()
            print("💡 You can manually trigger diagnosis from the Guardian Dashboard")

        print("=" * 60)
        print("✅ Test completed")


async def test_manual_diagnosis():
    """测试手动诊断功能"""
    print("\n🧪 Testing Manual Diagnosis...")
    print("=" * 60)

    async with async_session() as db:
        # 查找一个没有诊断的异常
        result = await db.execute(
            select(Anomaly)
            .where(Anomaly.ai_diagnosis == None)
            .order_by(Anomaly.detected_at.desc())
            .limit(1)
        )
        anomaly = result.scalar_one_or_none()

        if not anomaly:
            print("✅ All anomalies have been diagnosed")
            return

        print(f"Found undiagnosed anomaly #{anomaly.id}")
        print(f"  - Datasource: {anomaly.datasource_id}")
        print(f"  - Severity: {anomaly.severity}")
        print()

        # 获取数据源信息
        result = await db.execute(
            select(Datasource).where(Datasource.id == anomaly.datasource_id)
        )
        datasource = result.scalar_one_or_none()

        if datasource:
            print(f"Datasource: {datasource.name}")
            print(f"  - Type: {datasource.db_type}")
            print(f"  - Importance: {datasource.importance_level}")
            print()

        print("💡 To manually trigger diagnosis:")
        print(f"   POST /api/guardian/anomalies/{anomaly.datasource_id}/{anomaly.id}/diagnose")
        print()
        print("   Or use the 'Trigger AI Diagnosis' button in Guardian Dashboard")


if __name__ == "__main__":
    asyncio.run(test_diagnosis_trigger())
    asyncio.run(test_manual_diagnosis())
