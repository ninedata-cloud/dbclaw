"""
将旧的订阅配置迁移到新的 Channel 系统

执行时间：2026-03-18
"""

import asyncio
from sqlalchemy import select
from backend.database import async_session


async def migrate():
    """执行迁移"""
    async with async_session() as db:
        print("开始迁移：将旧订阅配置迁移到 Channel 系统...")

        from backend.models.alert_subscription import AlertSubscription
        from backend.models.integration import Integration, AlertChannel

        # 查询所有订阅
        result = await db.execute(select(AlertSubscription))
        subscriptions = result.scalars().all()

        migrated_count = 0
        skipped_count = 0

        for sub in subscriptions:
            # 如果已经有 channel_ids，跳过
            if sub.channel_ids:
                skipped_count += 1
                continue

            channel_ids = []

            # 迁移 webhook
            if "webhook" in sub.channels and sub.webhook_url:
                # 查找通用 Webhook Integration
                integration_result = await db.execute(
                    select(Integration).where(Integration.integration_id == "builtin_generic_webhook")
                )
                integration = integration_result.scalar_one_or_none()

                if integration:
                    # 创建 Channel
                    channel = AlertChannel(
                        name=f"订阅 {sub.id} 的 Webhook",
                        integration_id=integration.id,
                        params={"webhook_url": sub.webhook_url},
                        enabled=True,
                        user_id=sub.user_id
                    )
                    db.add(channel)
                    await db.flush()
                    channel_ids.append(channel.id)
                    print(f"  - 为订阅 {sub.id} 创建 Webhook Channel")

            # 迁移钉钉
            if "dingtalk" in sub.channels and sub.dingtalk_webhook_url:
                # 查找钉钉 Integration
                integration_result = await db.execute(
                    select(Integration).where(Integration.integration_id == "builtin_dingtalk_webhook")
                )
                integration = integration_result.scalar_one_or_none()

                if integration and sub.dingtalk_secret:
                    # 创建 Channel
                    channel = AlertChannel(
                        name=f"订阅 {sub.id} 的钉钉",
                        integration_id=integration.id,
                        params={
                            "webhook_url": sub.dingtalk_webhook_url,
                            "secret": sub.dingtalk_secret
                        },
                        enabled=True,
                        user_id=sub.user_id
                    )
                    db.add(channel)
                    await db.flush()
                    channel_ids.append(channel.id)
                    print(f"  - 为订阅 {sub.id} 创建钉钉 Channel")

            # 更新订阅
            if channel_ids:
                sub.channel_ids = channel_ids
                migrated_count += 1

        await db.commit()
        print(f"\n迁移完成！")
        print(f"  - 已迁移: {migrated_count} 个订阅")
        print(f"  - 已跳过: {skipped_count} 个订阅（已有 channel_ids）")


if __name__ == "__main__":
    asyncio.run(migrate())
