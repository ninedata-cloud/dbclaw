#!/usr/bin/env python3
"""
阿里云 RDS 集成完整测试脚本
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.system_config import SystemConfig
from backend.models.datasource import Datasource
from backend.models.integration import Integration
from backend.services.integration_service import IntegrationService
from sqlalchemy import select
import json


async def test_full_workflow():
    """完整测试流程"""

    # 创建数据库连接
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 80)
    print("阿里云 RDS 集成完整测试")
    print("=" * 80)

    async with async_session() as db:
        # 测试 1: 检查系统配置是否初始化
        print("\n[测试 1] 检查系统配置初始化")
        print("-" * 80)

        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == "aliyun_access_key_id")
        )
        ak_config = result.scalar_one_or_none()

        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == "aliyun_access_key_secret")
        )
        sk_config = result.scalar_one_or_none()

        if ak_config and sk_config:
            print(f"✓ 系统配置已初始化")
            print(f"  - aliyun_access_key_id: {ak_config.key} (category: {ak_config.category})")
            print(f"  - aliyun_access_key_secret: {sk_config.key} (category: {sk_config.category})")
        else:
            print(f"✗ 系统配置未初始化")
            return False

        # 测试 2: 检查阿里云 RDS 集成模板
        print("\n[测试 2] 检查阿里云 RDS 集成模板")
        print("-" * 80)

        result = await db.execute(
            select(Integration).where(Integration.integration_id == "builtin_aliyun_rds")
        )
        integration = result.scalar_one_or_none()

        if integration:
            print(f"✓ 集成模板已加载")
            print(f"  - ID: {integration.id}")
            print(f"  - 名称: {integration.name}")
            print(f"  - 类型: {integration.integration_type}")
            print(f"  - 启用: {integration.enabled}")

            # 检查配置 Schema
            schema = integration.config_schema
            if schema:
                print(f"  - 配置参数:")
                for key, prop in schema.get("properties", {}).items():
                    print(f"    * {key}: {prop.get('title', key)}")

                # 检查是否还有 access_key_id 参数
                if "access_key_id" in schema.get("properties", {}):
                    print(f"  ✗ 警告: 配置中仍包含 access_key_id 参数，应该已移除")
                else:
                    print(f"  ✓ 配置中已移除 access_key_id 参数")
        else:
            print(f"✗ 集成模板未加载，请先在界面上点击'加载内置模板'")
            return False

        # 测试 3: 检查数据源
        print("\n[测试 3] 检查测试数据源")
        print("-" * 80)

        result = await db.execute(select(Datasource).limit(5))
        datasources = result.scalars().all()

        if datasources:
            print(f"✓ 找到 {len(datasources)} 个数据源")
            for ds in datasources:
                ext_id = getattr(ds, "external_instance_id", None)
                print(f"  - {ds.name} ({ds.db_type})")
                print(f"    ID: {ds.id}, external_instance_id: {ext_id or '未配置'}")

            # 找一个有 external_instance_id 的数据源
            test_ds = None
            for ds in datasources:
                if getattr(ds, "external_instance_id", None):
                    test_ds = ds
                    break

            if test_ds:
                print(f"\n  ✓ 找到可用于测试的数据源: {test_ds.name} (ID: {test_ds.id})")
            else:
                print(f"\n  ✗ 没有配置 external_instance_id 的数据源")
                print(f"  提示: 请在数据源管理中配置 external_instance_id")
        else:
            print(f"✗ 没有数据源，请先创建数据源")
            return False

        # 测试 4: 测试未配置 AccessKey 的情况
        print("\n[测试 4] 测试未配置 AccessKey")
        print("-" * 80)

        if not ak_config.value or not sk_config.value:
            print("当前 AccessKey 未配置，测试预期行为...")

            test_params = {"region_id": "cn-hangzhou"}
            test_datasource_id = datasources[0].id if datasources else None

            if test_datasource_id:
                try:
                    result = await IntegrationService.test_integration(
                        db,
                        integration.id,
                        test_params,
                        None,
                        test_datasource_id
                    )

                    if result.get("success"):
                        print(f"✗ 测试应该失败但返回成功: {result}")
                        return False
                    else:
                        error_msg = result.get("message", "")
                        if "AccessKey" in error_msg or "未配置" in error_msg:
                            print(f"✓ 正确返回错误: {error_msg}")
                        else:
                            print(f"✗ 错误信息不明确: {error_msg}")
                            return False
                except Exception as e:
                    print(f"✗ 测试抛出异常: {e}")
                    return False
        else:
            print(f"AccessKey 已配置，跳过此测试")

        # 测试 5: 测试数据源没有 external_instance_id
        print("\n[测试 5] 测试数据源没有 external_instance_id")
        print("-" * 80)

        # 找一个没有 external_instance_id 的数据源
        no_ext_id_ds = None
        for ds in datasources:
            if not getattr(ds, "external_instance_id", None):
                no_ext_id_ds = ds
                break

        if no_ext_id_ds:
            print(f"使用数据源: {no_ext_id_ds.name} (ID: {no_ext_id_ds.id})")

            test_params = {"region_id": "cn-hangzhou"}

            try:
                result = await IntegrationService.test_integration(
                    db,
                    integration.id,
                    test_params,
                    None,
                    no_ext_id_ds.id
                )

                if result.get("success"):
                    print(f"✗ 测试应该失败但返回成功: {result}")
                    return False
                else:
                    error_msg = result.get("message", "")
                    if "external_instance_id" in error_msg or "未配置" in error_msg:
                        print(f"✓ 正确返回错误: {error_msg}")
                    else:
                        print(f"✗ 错误信息不明确: {error_msg}")
                        return False
            except Exception as e:
                print(f"✗ 测试抛出异常: {e}")
                return False
        else:
            print(f"所有数据源都配置了 external_instance_id，跳过此测试")

        # 测试 6: 代码语法检查
        print("\n[测试 6] 检查集成代码语法")
        print("-" * 80)

        try:
            # 尝试编译代码
            compile(integration.code, "<integration_code>", "exec")
            print(f"✓ 代码语法正确")

            # 检查代码中是否使用了 context.get_system_config
            if "context.get_system_config" in integration.code:
                print(f"✓ 代码中使用了 context.get_system_config")
            else:
                print(f"✗ 代码中未使用 context.get_system_config")
                return False

            # 检查代码中是否还有 params.get("access_key_id")
            if 'params.get("access_key_id")' in integration.code or "params['access_key_id']" in integration.code:
                print(f"✗ 代码中仍从 params 读取 access_key_id")
                return False
            else:
                print(f"✓ 代码中不再从 params 读取 access_key_id")

        except SyntaxError as e:
            print(f"✗ 代码语法错误: {e}")
            return False

        print("\n" + "=" * 80)
        print("测试总结")
        print("=" * 80)
        print("✓ 所有基础测试通过")
        print("\n下一步:")
        print("1. 在系统配置页面配置 aliyun_access_key_id 和 aliyun_access_key_secret")
        print("2. 确保数据源配置了 external_instance_id（阿里云 RDS 实例 ID）")
        print("3. 在集成管理页面测试阿里云 RDS 集成")

        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_full_workflow())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
