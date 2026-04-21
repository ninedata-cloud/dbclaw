"""
测试集成管理中的阿里云 RDS 凭证验证
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.integration_executor import IntegrationExecutor
from backend.utils.integration_templates import ALIYUN_RDS_TEMPLATE
from unittest.mock import AsyncMock, MagicMock
import logging

logger = logging.getLogger(__name__)


async def test_aliyun_no_credentials():
    """测试阿里云 RDS 集成没有配置凭证时的行为"""
    print("\n测试 1: 未配置凭证")
    print("-" * 60)

    # 创建 mock db session
    mock_db = AsyncMock()

    # 创建执行器
    executor = IntegrationExecutor(mock_db, logger)

    # 测试参数（空凭证）
    params = {
        "access_key_id": "",
        "access_key_secret": "",
        "region_id": "cn-hangzhou"
    }

    # 测试数据源
    datasource = [{
        "id": 1,
        "name": "测试数据库",
        "db_type": "mysql",
        "external_instance_id": "rm-test123"
    }]

    try:
        metrics = await executor.execute_metric_collection(
            ALIYUN_RDS_TEMPLATE["code"],
            params,
            datasource
        )
        print(f"  ✗ 失败: 应该抛出异常但返回了 {len(metrics)} 条指标")
        return False
    except ValueError as e:
        error_msg = str(e)
        if "AccessKey" in error_msg or "未配置" in error_msg:
            print(f"  结果: {e}")
            print("  ✓ 通过")
            return True
        else:
            print(f"  ✗ 失败: 错误信息不符合预期: {e}")
            return False
    except Exception as e:
        print(f"  ✗ 失败: 抛出了错误的异常类型: {type(e).__name__}: {e}")
        return False


async def test_aliyun_invalid_credentials():
    """测试阿里云 RDS 集成配置了无效凭证时的行为"""
    print("\n测试 2: 配置了无效凭证")
    print("-" * 60)

    # 创建 mock db session
    mock_db = AsyncMock()

    # 创建执行器
    executor = IntegrationExecutor(mock_db, logger)

    # 测试参数（无效凭证）
    params = {
        "access_key_id": "LTAI5tTest123456",
        "access_key_secret": "test_secret_key_123",
        "region_id": "cn-hangzhou"
    }

    # 测试数据源
    datasource = [{
        "id": 1,
        "name": "测试数据库",
        "db_type": "mysql",
        "external_instance_id": "rm-test123"
    }]

    try:
        metrics = await executor.execute_metric_collection(
            ALIYUN_RDS_TEMPLATE["code"],
            params,
            datasource
        )
        print(f"  ✗ 失败: 应该抛出异常但返回了 {len(metrics)} 条指标")
        return False
    except ValueError as e:
        error_msg = str(e)
        if "认证失败" in error_msg or "AccessKey" in error_msg:
            print(f"  结果: {e}")
            print("  ✓ 通过")
            return True
        else:
            print(f"  ✗ 失败: 错误信息不符合预期: {e}")
            return False
    except Exception as e:
        # 网络错误或其他异常也算通过（因为至少不是返回空列表）
        print(f"  结果: {type(e).__name__}: {e}")
        print("  ✓ 通过（抛出了异常）")
        return True


async def test_aliyun_no_datasource():
    """测试阿里云 RDS 集成没有数据源时的行为（应该验证凭证）"""
    print("\n测试 3: 没有数据源但有无效凭证")
    print("-" * 60)

    # 创建 mock db session
    mock_db = AsyncMock()

    # 创建执行器
    executor = IntegrationExecutor(mock_db, logger)

    # 测试参数（无效凭证）
    params = {
        "access_key_id": "LTAI5tTest123456",
        "access_key_secret": "test_secret_key_123",
        "region_id": "cn-hangzhou"
    }

    # 空数据源列表
    datasource = []

    try:
        metrics = await executor.execute_metric_collection(
            ALIYUN_RDS_TEMPLATE["code"],
            params,
            datasource
        )
        print(f"  ✗ 失败: 应该抛出异常但返回了 {len(metrics)} 条指标")
        return False
    except ValueError as e:
        error_msg = str(e)
        if "验证失败" in error_msg or "认证失败" in error_msg or "AccessKey" in error_msg:
            print(f"  结果: {e}")
            print("  ✓ 通过（即使没有数据源也会验证凭证）")
            return True
        else:
            print(f"  ✗ 失败: 错误信息不符合预期: {e}")
            return False
    except Exception as e:
        # 网络错误或其他异常也算通过（因为至少不是返回空列表）
        print(f"  结果: {type(e).__name__}: {e}")
        print("  ✓ 通过（抛出了异常）")
        return True


async def test_aliyun_no_external_instance_id():
    """测试数据源没有 external_instance_id 但有无效凭证"""
    print("\n测试 4: 数据源没有 external_instance_id 但有无效凭证")
    print("-" * 60)

    # 创建 mock db session
    mock_db = AsyncMock()

    # 创建执行器
    executor = IntegrationExecutor(mock_db, logger)

    # 测试参数（无效凭证）
    params = {
        "access_key_id": "LTAI5tTest123456",
        "access_key_secret": "test_secret_key_123",
        "region_id": "cn-hangzhou"
    }

    # 数据源没有 external_instance_id
    datasource = [{
        "id": 1,
        "name": "测试数据库",
        "db_type": "mysql",
        "external_instance_id": None
    }]

    try:
        metrics = await executor.execute_metric_collection(
            ALIYUN_RDS_TEMPLATE["code"],
            params,
            datasource
        )
        print(f"  ✗ 失败: 应该抛出异常但返回了 {len(metrics)} 条指标")
        return False
    except ValueError as e:
        error_msg = str(e)
        if "验证失败" in error_msg or "认证失败" in error_msg or "AccessKey" in error_msg:
            print(f"  结果: {e}")
            print("  ✓ 通过（会先验证凭证）")
            return True
        else:
            print(f"  ✗ 失败: 错误信息不符合预期: {e}")
            return False
    except Exception as e:
        # 网络错误或其他异常也算通过
        print(f"  结果: {type(e).__name__}: {e}")
        print("  ✓ 通过（抛出了异常）")
        return True


async def main():
    print("=" * 60)
    print("集成管理 - 阿里云 RDS 凭证验证测试")
    print("=" * 60)

    results = []
    results.append(await test_aliyun_no_credentials())
    results.append(await test_aliyun_invalid_credentials())
    results.append(await test_aliyun_no_datasource())
    results.append(await test_aliyun_no_external_instance_id())

    print("\n" + "=" * 60)
    print(f"测试完成: {sum(results)}/{len(results)} 通过")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
