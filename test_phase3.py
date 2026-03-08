"""
Test Phase 3 Proactive Diagnosis
测试主动诊断功能
"""
import asyncio
import sys
from sqlalchemy import select

sys.path.insert(0, '.')

# 确保所有模型都被导入
from backend.database import async_session
from backend.models.user import User
from backend.models.datasource import Datasource
from backend.models.baseline import MetricBaseline
from backend.models.importance import DatasourceImportance
from backend.models.anomaly import Anomaly
from backend.models.diagnostic_case import DiagnosticCase, GuardianAlert
from backend.models.guardian_rule import GuardianRule, RuleExecution
from backend.models.diagnostic_session import DiagnosticSession
from backend.models.ssh_host import SSHHost
from backend.services.proactive_diagnosis import ProactiveDiagnosisService


async def test_proactive_diagnosis():
    """测试主动诊断功能"""

    print("🧪 Testing Phase 3 Proactive Diagnosis...")
    print("=" * 60)

    async with async_session() as db:
        # 1. 查找一个未诊断的异常
        result = await db.execute(
            select(Anomaly)
            .where(Anomaly.ai_diagnosis == None)
            .order_by(Anomaly.detected_at.desc())
            .limit(1)
        )
        anomaly = result.scalar_one_or_none()

        if not anomaly:
            print("❌ No undiagnosed anomaly found")
            print("\nTip: Wait for anomaly detection to create new anomalies")
            return

        print(f"✓ Found anomaly #{anomaly.id}")
        print(f"  - Datasource ID: {anomaly.datasource_id}")
        print(f"  - Severity: {anomaly.severity}")
        print(f"  - Detected at: {anomaly.detected_at}")
        print(f"  - Current status: {anomaly.status}")
        print()

        # 2. 触发主动诊断
        print("🔍 Triggering proactive diagnosis...")
        service = ProactiveDiagnosisService()

        result = await service.diagnose_anomaly(
            db=db,
            anomaly_id=anomaly.id,
            auto_fix=False
        )

        print()
        print("=" * 60)

        if result.get("success"):
            print("✅ Proactive diagnosis completed successfully!")
            print()
            print(f"Anomaly ID: {result['anomaly_id']}")
            print()
            print("Root Cause:")
            print("-" * 60)
            print(result.get('root_cause', 'N/A'))
            print()
            print("Recommended Actions:")
            print("-" * 60)
            for i, action in enumerate(result.get('recommended_actions', []), 1):
                print(f"{i}. {action}")
            print()

            if result.get('alert_id'):
                print(f"Alert created: #{result['alert_id']}")
        else:
            print(f"❌ Diagnosis failed: {result.get('error')}")

        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_proactive_diagnosis())
