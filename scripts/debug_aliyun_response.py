#!/usr/bin/env python3
"""
调试阿里云 API 返回的原始数据
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.integration import Integration
from backend.services.integration_service import IntegrationService
from sqlalchemy import select
import json


async def debug_response():
    """调试阿里云 API 响应"""

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 获取集成
        result = await db.execute(
            select(Integration).where(Integration.integration_id == "builtin_aliyun_rds")
        )
        integration = result.scalar_one_or_none()

        if not integration:
            print("✗ 集成模板未加载")
            return

        # 测试参数
        test_params = {"region_id": "cn-hangzhou"}
        test_datasource_id = 9

        print(f"执行测试...")

        try:
            result = await IntegrationService.test_integration(
                db,
                integration.id,
                test_params,
                None,
                test_datasource_id
            )

            if not result.get("success"):
                print(f"✗ 测试失败: {result.get('message')}")
                return

            metrics = result.get("data", {}).get("metrics", [])

            print(f"\n返回的指标数量: {len(metrics)}")

            # 按 metric_name 分组
            from collections import defaultdict
            metric_groups = defaultdict(list)
            for metric in metrics:
                metric_name = metric.get("metric_name")
                metric_groups[metric_name].append(metric)

            print(f"\n指标类型统计:")
            for metric_name, items in metric_groups.items():
                print(f"  - {metric_name}: {len(items)} 条")

            # 显示前几条原始数据
            print(f"\n前 5 条原始数据:")
            for i, metric in enumerate(metrics[:5], 1):
                print(f"\n{i}. {json.dumps(metric, indent=2, ensure_ascii=False)}")

        except Exception as e:
            print(f"\n✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_response())
