#!/usr/bin/env python3
"""
测试告警聚合逻辑
"""
import asyncio
import sys
sys.path.insert(0, '/Users/william/prog2/temp/smartdba')

from backend.database import async_session
from backend.services.alert_service import AlertService
from backend.services.alert_event_service import AlertEventService
from backend.services.aggregation_engine import AggregationEngine
from sqlalchemy import select
from backend.models.alert_message import AlertMessage
from backend.models.alert_event import AlertEvent
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.models.alert_subscription import AlertSubscription


async def test_aggregation():
    """测试告警聚合逻辑"""
    async with async_session() as db:
        print("=" * 60)
        print("告警聚合逻辑测试")
        print("=" * 60)

        # 1. 查询最近的告警
        result = await db.execute(
            select(AlertMessage)
            .order_by(AlertMessage.created_at.desc())
            .limit(10)
        )
        recent_alerts = result.scalars().all()

        print(f"\n最近的 {len(recent_alerts)} 条告警:")
        for alert in recent_alerts:
            print(f"  - Alert {alert.id}: {alert.title}")
            print(f"    数据源: {alert.datasource_id}, 类型: {alert.alert_type}")
            print(f"    事件ID: {alert.event_id}, 状态: {alert.status}")
            print(f"    创建时间: {alert.created_at}")

        # 2. 查询事件
        result = await db.execute(
            select(AlertEvent)
            .order_by(AlertEvent.event_start_time.desc())
            .limit(5)
        )
        recent_events = result.scalars().all()

        print(f"\n最近的 {len(recent_events)} 个事件:")
        for event in recent_events:
            print(f"  - Event {event.id}: {event.title}")
            print(f"    聚合键: {event.aggregation_key}")
            print(f"    告警数量: {event.alert_count}")
            print(f"    开始时间: {event.event_start_time}")
            print(f"    结束时间: {event.event_end_time}")

        # 3. 查询投递日志
        result = await db.execute(
            select(AlertDeliveryLog)
            .order_by(AlertDeliveryLog.created_at.desc())
            .limit(10)
        )
        recent_logs = result.scalars().all()

        print(f"\n最近的 {len(recent_logs)} 条投递日志:")
        for log in recent_logs:
            print(f"  - Log {log.id}: Alert {log.alert_id}")
            print(f"    订阅: {log.subscription_id}, 渠道: {log.channel}")
            print(f"    状态: {log.status}, 发送时间: {log.sent_at}")
            print(f"    创建时间: {log.created_at}")

        # 4. 测试聚合逻辑
        if recent_alerts:
            test_alert = recent_alerts[0]
            print(f"\n测试告警 {test_alert.id} 的聚合逻辑:")

            # 获取订阅
            result = await db.execute(
                select(AlertSubscription).where(AlertSubscription.enabled == True)
            )
            subscriptions = result.scalars().all()

            if subscriptions:
                for sub in subscriptions:
                    should_send = await AggregationEngine.should_send_alert(
                        db, test_alert, sub
                    )
                    print(f"  - 订阅 {sub.id}: {'✓ 应该发送' if should_send else '✗ 应该抑制'}")
            else:
                print("  没有找到启用的订阅")

        # 5. 统计信息
        print("\n统计信息:")

        # 统计活跃告警
        result = await db.execute(
            select(AlertMessage).where(AlertMessage.status == "active")
        )
        active_alerts = result.scalars().all()
        print(f"  - 活跃告警数: {len(active_alerts)}")

        # 统计活跃事件
        result = await db.execute(
            select(AlertEvent).where(AlertEvent.status == "active")
        )
        active_events = result.scalars().all()
        print(f"  - 活跃事件数: {len(active_events)}")

        # 统计最近1小时的投递
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=1)
        result = await db.execute(
            select(AlertDeliveryLog).where(
                AlertDeliveryLog.created_at >= cutoff
            )
        )
        recent_deliveries = result.scalars().all()
        print(f"  - 最近1小时投递数: {len(recent_deliveries)}")

        # 统计成功投递
        successful = [log for log in recent_deliveries if log.status == "sent"]
        print(f"  - 成功投递数: {len(successful)}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_aggregation())
