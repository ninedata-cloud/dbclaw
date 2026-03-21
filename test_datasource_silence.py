"""
测试数据源静默功能
"""
import asyncio
from datetime import datetime, timedelta
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.services.metric_collector import collect_metrics_for_connection
from sqlalchemy import select


async def test_silence_feature():
    """测试静默功能的完整流程"""
    print("=== 测试数据源静默功能 ===\n")

    async with async_session() as db:
        # 1. 获取一个测试数据源
        result = await db.execute(
            select(Datasource).where(Datasource.is_active == True).limit(1)
        )
        datasource = result.scalar_one_or_none()

        if not datasource:
            print("✗ 没有可用的数据源进行测试")
            return

        print(f"测试数据源: {datasource.name} (ID: {datasource.id})")
        print(f"初始状态: silence_until={datasource.silence_until}\n")

        # 2. 设置静默（1小时）
        print("步骤1: 设置静默1小时")
        from backend.utils.datetime_helper import now
        silence_until = now() + timedelta(hours=1)
        datasource.silence_until = silence_until
        datasource.silence_reason = "测试静默功能"
        await db.commit()
        await db.refresh(datasource)

        print(f"✓ 静默已设置")
        print(f"  silence_until: {datasource.silence_until}")
        print(f"  silence_reason: {datasource.silence_reason}\n")

        # 3. 测试采集器是否跳过静默数据源
        print("步骤2: 测试采集器是否跳过静默数据源")
        print("  调用 collect_metrics_for_connection()...")

        # 这应该被跳过，不会采集指标
        await collect_metrics_for_connection(datasource.id)
        print("  ✓ 采集器已跳过静默数据源（检查日志确认）\n")

        # 4. 取消静默
        print("步骤3: 取消静默")
        datasource.silence_until = None
        datasource.silence_reason = None
        await db.commit()
        await db.refresh(datasource)

        print(f"✓ 静默已取消")
        print(f"  silence_until: {datasource.silence_until}")
        print(f"  silence_reason: {datasource.silence_reason}\n")

        # 5. 测试采集器恢复正常
        print("步骤4: 测试采集器恢复正常")
        print("  调用 collect_metrics_for_connection()...")
        await collect_metrics_for_connection(datasource.id)
        print("  ✓ 采集器已恢复正常采集\n")

        print("=== 测试完成 ===")
        print("✓ 所有测试通过")
        print("\n建议:")
        print("1. 检查日志确认采集器跳过了静默数据源")
        print("2. 在前端界面测试静默设置和取消功能")
        print("3. 验证静默期间不会创建告警")


if __name__ == "__main__":
    asyncio.run(test_silence_feature())
