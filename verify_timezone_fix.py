"""
验证时区修复
"""
import asyncio
from datetime import datetime
from backend.database import async_session
from backend.models.metric_snapshot import MetricSnapshot
from backend.utils.datetime_helper import now
from sqlalchemy import select, desc


async def verify_fix():
    """验证时区修复"""
    async with async_session() as db:
        # 获取最新的几条记录
        result = await db.execute(
            select(MetricSnapshot)
            .order_by(desc(MetricSnapshot.collected_at))
            .limit(5)
        )
        metrics = result.scalars().all()

        print("最新的 5 条记录:")
        print("-" * 80)
        current_time = now()
        print(f"当前本地时间: {current_time}")
        print("-" * 80)

        for m in metrics:
            time_diff = (current_time - m.collected_at).total_seconds()
            print(f"ID: {m.id}")
            print(f"  采集时间: {m.collected_at}")
            print(f"  距现在: {time_diff:.0f} 秒 ({time_diff/60:.1f} 分钟)")
            print(f"  数据源: {m.datasource_id}")
            print()

        # 检查时间是否合理（最新记录应该在最近几分钟内）
        if metrics:
            latest = metrics[0]
            time_diff = (current_time - latest.collected_at).total_seconds()
            if time_diff < 0:
                print("⚠️  警告: 最新记录的时间在未来！时区可能仍有问题")
            elif time_diff > 3600:
                print("⚠️  警告: 最新记录超过1小时前，可能采集服务未运行")
            else:
                print("✓ 时区修复成功！最新记录时间正常")


if __name__ == '__main__':
    asyncio.run(verify_fix())
