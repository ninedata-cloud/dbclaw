#!/usr/bin/env python3
"""
测试有 external_instance_id 的数据源
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.integration import Integration
from backend.services.integration_service import IntegrationService
from sqlalchemy import select


async def test_with_valid_datasource():
    """测试有 external_instance_id 的数据源"""

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 80)
    print("测试阿里云 RDS 集成（有 external_instance_id 的数据源）")
    print("=" * 80)

    async with async_session() as db:
        # 获取集成
        result = await db.execute(
            select(Integration).where(Integration.integration_id == "builtin_aliyun_rds")
        )
        integration = result.scalar_one_or_none()

        if not integration:
            print("✗ 集成模板未加载")
            return False

        # 测试参数
        test_params = {"region_id": "cn-hangzhou"}
        test_datasource_id = 9  # rm-bp16knn4mo4fvh99ieo

        print(f"\n测试参数:")
        print(f"  - 集成 ID: {integration.id}")
        print(f"  - 数据源 ID: {test_datasource_id}")
        print(f"  - 地域: {test_params['region_id']}")

        print(f"\n执行测试...")

        try:
            result = await IntegrationService.test_integration(
                db,
                integration.id,
                test_params,
                None,
                test_datasource_id
            )

            print(f"\n测试结果:")
            print(f"  - success: {result.get('success')}")
            print(f"  - message: {result.get('message')}")

            if result.get("data"):
                metrics = result.get("data", {}).get("metrics", [])
                print(f"  - 指标数量: {len(metrics)}")
                if metrics:
                    print(f"\n前 3 条指标:")
                    for i, metric in enumerate(metrics[:3]):
                        print(f"    {i+1}. {metric.get('metric_name')}: {metric.get('metric_value')} ({metric.get('timestamp')})")

            if result.get("success"):
                print(f"\n✓ 测试成功")
                return True
            else:
                print(f"\n✗ 测试失败")
                return False

        except Exception as e:
            print(f"\n✗ 测试抛出异常: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_with_valid_datasource())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
