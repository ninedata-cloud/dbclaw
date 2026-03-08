"""
手动触发 AI 诊断
用于测试诊断功能是否正常工作
"""
import asyncio
import sys
from sqlalchemy import select

sys.path.insert(0, 'backend')

from backend.database import async_session
from backend.models.anomaly import Anomaly
from backend.services.proactive_diagnosis import ProactiveDiagnosisService


async def trigger_diagnosis_for_anomaly(anomaly_id: int):
    """手动触发指定异常的诊断"""
    print(f"🔍 Triggering diagnosis for anomaly #{anomaly_id}...")
    print("=" * 60)

    async with async_session() as db:
        # 获取异常信息
        result = await db.execute(
            select(Anomaly).where(Anomaly.id == anomaly_id)
        )
        anomaly = result.scalar_one_or_none()

        if not anomaly:
            print(f"❌ Anomaly #{anomaly_id} not found")
            return

        print(f"Anomaly Details:")
        print(f"  - Datasource: {anomaly.datasource_id}")
        print(f"  - Type: {anomaly.anomaly_type}")
        print(f"  - Severity: {anomaly.severity}")
        print(f"  - Status: {anomaly.status}")
        print(f"  - Detected at: {anomaly.detected_at}")
        print()

        if anomaly.ai_diagnosis:
            print("⚠️  This anomaly already has a diagnosis")
            print(f"Diagnosis length: {len(anomaly.ai_diagnosis)} chars")
            print()
            user_input = input("Re-diagnose? (y/n): ")
            if user_input.lower() != 'y':
                return

        # 触发诊断
        print("Starting diagnosis...")
        diagnosis_service = ProactiveDiagnosisService()

        try:
            result = await diagnosis_service.diagnose_anomaly(
                db, anomaly_id, auto_fix=False
            )

            if result.get("success"):
                print()
                print("=" * 60)
                print("✅ Diagnosis completed successfully!")
                print("=" * 60)
                print()
                print("Root Cause:")
                print(result.get("root_cause", "N/A"))
                print()
                print("Recommended Actions:")
                for i, action in enumerate(result.get("recommended_actions", []), 1):
                    print(f"  {i}. {action}")
                print()
                print("Full Diagnosis:")
                print("-" * 60)
                print(result.get("diagnosis", "N/A"))
            else:
                print()
                print("❌ Diagnosis failed:")
                print(result.get("error", "Unknown error"))

        except Exception as e:
            print()
            print(f"❌ Exception during diagnosis: {e}")
            import traceback
            traceback.print_exc()


async def trigger_latest_undiagnosed():
    """触发最新的未诊断异常"""
    async with async_session() as db:
        result = await db.execute(
            select(Anomaly)
            .where(Anomaly.ai_diagnosis == None)
            .where(Anomaly.status == 'detected')
            .order_by(Anomaly.detected_at.desc())
            .limit(1)
        )
        anomaly = result.scalar_one_or_none()

        if not anomaly:
            print("✅ No undiagnosed anomalies found")
            return

        await trigger_diagnosis_for_anomaly(anomaly.id)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 指定异常 ID
        anomaly_id = int(sys.argv[1])
        asyncio.run(trigger_diagnosis_for_anomaly(anomaly_id))
    else:
        # 诊断最新的未诊断异常
        print("No anomaly ID specified, diagnosing latest undiagnosed anomaly...")
        print()
        asyncio.run(trigger_latest_undiagnosed())
