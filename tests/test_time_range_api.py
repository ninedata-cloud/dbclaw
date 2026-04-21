"""
测试时间范围查询 API
"""
import asyncio
from datetime import datetime, timedelta
from backend.database import async_session
from backend.models.datasource_metric import DatasourceMetric
from backend.utils.datetime_helper import now
from sqlalchemy import select, desc


async def test_time_range_query():
    """测试时间范围查询"""
    async with async_session() as db:
        # 测试 1: 查询最近 60 分钟
        print("测试 1: 查询最近 60 分钟")
        start_time = now() - timedelta(minutes=60)
        result = await db.execute(
            select(DatasourceMetric)
            .where(
                DatasourceMetric.datasource_id == 1,
                DatasourceMetric.metric_type == 'db_status',
                DatasourceMetric.collected_at >= start_time
            )
            .order_by(desc(DatasourceMetric.collected_at))
            .limit(1000)
        )
        metrics = result.scalars().all()
        print(f"  找到 {len(metrics)} 条记录")
        if metrics:
            print(f"  最早: {metrics[-1].collected_at}")
            print(f"  最新: {metrics[0].collected_at}")

        # 测试 2: 查询自定义时间范围
        print("\n测试 2: 查询自定义时间范围 (最近 2 小时到 1 小时)")
        start = now() - timedelta(hours=2)
        end = now() - timedelta(hours=1)
        result = await db.execute(
            select(DatasourceMetric)
            .where(
                DatasourceMetric.datasource_id == 1,
                DatasourceMetric.metric_type == 'db_status',
                DatasourceMetric.collected_at >= start,
                DatasourceMetric.collected_at <= end
            )
            .order_by(desc(DatasourceMetric.collected_at))
            .limit(1000)
        )
        metrics = result.scalars().all()
        print(f"  找到 {len(metrics)} 条记录")
        if metrics:
            print(f"  最早: {metrics[-1].collected_at}")
            print(f"  最新: {metrics[0].collected_at}")

        # 测试 3: 查询最近 1 天
        print("\n测试 3: 查询最近 1 天")
        start_time = now() - timedelta(days=1)
        result = await db.execute(
            select(DatasourceMetric)
            .where(
                DatasourceMetric.datasource_id == 1,
                DatasourceMetric.metric_type == 'db_status',
                DatasourceMetric.collected_at >= start_time
            )
            .order_by(desc(DatasourceMetric.collected_at))
            .limit(10000)
        )
        metrics = result.scalars().all()
        print(f"  找到 {len(metrics)} 条记录")
        if metrics:
            print(f"  最早: {metrics[-1].collected_at}")
            print(f"  最新: {metrics[0].collected_at}")


if __name__ == '__main__':
    asyncio.run(test_time_range_query())
