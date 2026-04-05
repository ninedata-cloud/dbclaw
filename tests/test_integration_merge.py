#!/usr/bin/env python3
"""
测试集成指标合并到 db_status 的逻辑
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, and_, desc
from backend.config import settings
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.datasource import Datasource
from backend.models.integration import Integration
from datetime import datetime
import json


async def test_integration_merge():
    """测试集成指标合并逻辑"""

    # 创建数据库连接
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 80)
    print("测试集成指标合并到 db_status")
    print("=" * 80)

    async with async_session_factory() as session:
        # 1. 查找一个使用集成采集的数据源
        print("\n[步骤 1] 查找使用集成采集的数据源")
        print("-" * 80)

        result = await session.execute(
            select(Datasource).where(
                and_(
                    Datasource.metric_source == 'integration',
                    Datasource.is_active == True
                )
            ).limit(1)
        )
        datasource = result.scalar_one_or_none()

        if not datasource:
            print("✗ 未找到使用集成采集的数据源")
            print("  请在前端界面配置一个数据源，设置 metric_source 为 'integration'")
            return

        print(f"✓ 找到数据源: {datasource.name} (ID: {datasource.id})")
        print(f"  - 数据库类型: {datasource.db_type}")
        print(f"  - 外部实例 ID: {datasource.external_instance_id or '未配置'}")

        # 2. 查询该数据源最新的 db_status 快照
        print("\n[步骤 2] 查询最新的 db_status 快照")
        print("-" * 80)

        result = await session.execute(
            select(MetricSnapshot)
            .where(
                and_(
                    MetricSnapshot.datasource_id == datasource.id,
                    MetricSnapshot.metric_type == "db_status"
                )
            )
            .order_by(desc(MetricSnapshot.collected_at))
            .limit(5)
        )
        snapshots = result.scalars().all()

        if not snapshots:
            print("✗ 未找到 db_status 快照")
            print("  请等待指标采集完成，或手动触发采集")
            return

        print(f"✓ 找到 {len(snapshots)} 个最新快照")

        for i, snapshot in enumerate(snapshots):
            print(f"\n  快照 {i+1}:")
            print(f"    - 采集时间: {snapshot.collected_at}")
            print(f"    - 指标类型: {snapshot.metric_type}")

            # 检查是否包含 CPU 和内存指标
            data = snapshot.data or {}
            cpu_usage = data.get('cpu_usage')
            memory_usage = data.get('memory_usage')

            if cpu_usage is not None:
                print(f"    - CPU 使用率: {cpu_usage}%")
            else:
                print(f"    - CPU 使用率: 未采集")

            if memory_usage is not None:
                print(f"    - 内存使用率: {memory_usage}%")
            else:
                print(f"    - 内存使用率: 未采集")

            # 显示其他关键指标
            other_metrics = []
            for key in ['qps', 'tps', 'active_connections', 'iops', 'disk_usage']:
                if key in data:
                    other_metrics.append(f"{key}={data[key]}")

            if other_metrics:
                print(f"    - 其他指标: {', '.join(other_metrics)}")

        # 3. 查询是否有 integration_metric 类型的快照（旧格式）
        print("\n[步骤 3] 检查是否有旧格式的 integration_metric 快照")
        print("-" * 80)

        result = await session.execute(
            select(MetricSnapshot)
            .where(
                and_(
                    MetricSnapshot.datasource_id == datasource.id,
                    MetricSnapshot.metric_type == "integration_metric"
                )
            )
            .order_by(desc(MetricSnapshot.collected_at))
            .limit(3)
        )
        old_snapshots = result.scalars().all()

        if old_snapshots:
            print(f"⚠ 找到 {len(old_snapshots)} 个旧格式的 integration_metric 快照")
            print("  这些快照使用旧的数据格式，前端无法正常显示")
            print("  修改后的代码会将新采集的指标合并到 db_status 中")
        else:
            print("✓ 未找到旧格式的快照，说明已经使用新的合并逻辑")

        # 4. 检查集成配置
        print("\n[步骤 4] 检查集成配置")
        print("-" * 80)

        result = await session.execute(
            select(Integration).where(
                and_(
                    Integration.integration_type == 'inbound_metric',
                    Integration.enabled == True
                )
            )
        )
        integrations = result.scalars().all()

        if integrations:
            print(f"✓ 找到 {len(integrations)} 个启用的监控集成")
            for integration in integrations:
                print(f"  - {integration.name} (ID: {integration.id})")
                print(f"    最后运行: {integration.last_run_at or '从未运行'}")
                if integration.last_error:
                    print(f"    最后错误: {integration.last_error}")
        else:
            print("✗ 未找到启用的监控集成")
            print("  请在前端界面启用阿里云 RDS 集成")

        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)

        # 总结
        print("\n总结:")
        if snapshots and (snapshots[0].data.get('cpu_usage') is not None or snapshots[0].data.get('memory_usage') is not None):
            print("✓ 最新的 db_status 快照包含 CPU/内存指标，修改生效！")
        else:
            print("⚠ 最新的 db_status 快照不包含 CPU/内存指标")
            print("  可能原因:")
            print("  1. 集成尚未运行（等待下一次调度）")
            print("  2. 数据源未配置 external_instance_id")
            print("  3. 阿里云 API 调用失败")
            print("  请检查日志或手动触发集成执行")


if __name__ == "__main__":
    asyncio.run(test_integration_merge())
