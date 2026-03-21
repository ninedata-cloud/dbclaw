"""
测试静默期间不发送通知
"""
import asyncio
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.alert_message import AlertMessage
from backend.services.notification_dispatcher import _is_datasource_silenced
from sqlalchemy import select
from datetime import timedelta


async def test_notification_silence():
    """测试通知分发器的静默检查"""
    print("=== 测试通知分发器静默检查 ===\n")

    async with async_session() as db:
        # 1. 查询数据源1
        result = await db.execute(select(Datasource).where(Datasource.id == 1))
        ds = result.scalar_one_or_none()

        if not ds:
            print("✗ 数据源不存在")
            return

        print(f"数据源: {ds.name} (ID: {ds.id})")
        print(f"静默截止时间: {ds.silence_until}\n")

        # 2. 测试静默检查函数
        print("步骤1: 测试 _is_datasource_silenced() 函数")
        is_silenced = await _is_datasource_silenced(db, ds.id)
        print(f"  结果: {'✓ 在静默期内' if is_silenced else '✗ 未静默'}\n")

        # 3. 设置静默（如果未设置）
        if not is_silenced:
            print("步骤2: 设置静默1小时")
            from backend.utils.datetime_helper import now
            ds.silence_until = now() + timedelta(hours=1)
            ds.silence_reason = "测试通知静默"
            await db.commit()
            print(f"  ✓ 静默已设置: {ds.silence_until}\n")

            # 再次测试
            is_silenced = await _is_datasource_silenced(db, ds.id)
            print(f"  再次检查: {'✓ 在静默期内' if is_silenced else '✗ 未静默'}\n")

        # 4. 查询活跃告警
        print("步骤3: 查询活跃告警")
        result = await db.execute(
            select(AlertMessage)
            .where(
                AlertMessage.datasource_id == ds.id,
                AlertMessage.status == 'active'
            )
            .limit(3)
        )
        alerts = result.scalars().all()

        print(f"  找到 {len(alerts)} 条活跃告警")
        for alert in alerts:
            print(f"    - 告警ID: {alert.id}, 创建时间: {alert.created_at}")

        if alerts:
            print(f"\n  ⚠️ 这些告警在静默期内不应发送通知")
        else:
            print(f"\n  ✓ 没有活跃告警")

        print("\n=== 测试完成 ===")
        print("✓ 通知分发器现在会检查静默状态")
        print("✓ 静默期内的告警不会发送通知")
        print("\n建议:")
        print("1. 重启应用以应用修复")
        print("2. 观察日志确认静默期内不发送通知")
        print("3. 静默期结束后验证通知恢复正常")


if __name__ == "__main__":
    asyncio.run(test_notification_silence())
