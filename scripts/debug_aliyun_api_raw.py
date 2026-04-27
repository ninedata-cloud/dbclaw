#!/usr/bin/env python3
"""
直接调用阿里云 SDK 查看原始响应
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.system_config import SystemConfig
from sqlalchemy import select
from datetime import datetime, timedelta
import json


async def test_raw_api():
    """直接测试阿里云 API"""

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 获取 AccessKey
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == "aliyun_access_key_id")
        )
        ak_config = result.scalar_one_or_none()

        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == "aliyun_access_key_secret")
        )
        sk_config = result.scalar_one_or_none()

        if not ak_config or not sk_config or not ak_config.value or not sk_config.value:
            print("✗ AccessKey 未配置")
            return

        access_key_id = ak_config.value
        access_key_secret = sk_config.value

        # 导入阿里云 SDK
        try:
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkrds.request.v20140815 import DescribeDBInstancePerformanceRequest
        except ImportError:
            print("✗ 阿里云 SDK 未安装")
            return

        region_id = "cn-hangzhou"
        instance_id = "rm-bp16knn4mo4fvh99i"

        # 创建客户端
        client = AcsClient(access_key_id, access_key_secret, region_id)

        # 时间范围
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)

        # 定义要查询的指标
        metric_mappings = {
            "MySQL_MemCpuUsage": [
                ("cpu_usage", 0, "%"),
                ("memory_usage", 1, "%")
            ],
            "MySQL_DetailedSpaceUsage": [
                ("disk_total", 0, "MB"),
                ("disk_data", 1, "MB"),
                ("disk_log", 2, "MB"),
                ("disk_temp", 3, "MB"),
                ("disk_system", 4, "MB")
            ],
            "MySQL_IOPS": [
                ("iops", 0, "次/秒")
            ],
            "MySQL_MBPS": [
                ("throughput", 0, "Byte/秒")
            ],
            "MySQL_NetworkTraffic": [
                ("network_in", 0, "KB/秒"),
                ("network_out", 1, "KB/秒")
            ],
            "MySQL_QPSTPS": [
                ("qps", 0, "次/秒"),
                ("tps", 1, "个/秒")
            ],
            "MySQL_Sessions": [
                ("active_connections", 0, "个"),
                ("total_connections", 1, "个")
            ]
        }

        keys = ",".join(metric_mappings.keys())

        print(f"查询参数:")
        print(f"  - Instance ID: {instance_id}")
        print(f"  - Region: {region_id}")
        print(f"  - Keys: {keys}")
        print(f"  - StartTime: {start_time.strftime('%Y-%m-%dT%H:%MZ')}")
        print(f"  - EndTime: {end_time.strftime('%Y-%m-%dT%H:%MZ')}")

        # 创建请求
        request = DescribeDBInstancePerformanceRequest.DescribeDBInstancePerformanceRequest()
        request.set_DBInstanceId(instance_id)
        request.set_Key(keys)
        request.set_StartTime(start_time.strftime("%Y-%m-%dT%H:%MZ"))
        request.set_EndTime(end_time.strftime("%Y-%m-%dT%H:%MZ"))

        # 发送请求
        try:
            response = client.do_action_with_exception(request)
            data = json.loads(response)

            print(f"\n✓ API 调用成功")
            print(f"\n原始响应:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

            # 解析性能数据
            perf_keys = data.get("PerformanceKeys", {}).get("PerformanceKey", [])
            print(f"\n返回的指标类型数量: {len(perf_keys)}")

            for perf_key in perf_keys:
                metric_name = perf_key.get("Key")
                values = perf_key.get("Values", {}).get("PerformanceValue", [])
                print(f"\n指标: {metric_name}")
                print(f"  - 数据点数量: {len(values)}")
                if values:
                    sample = values[0]
                    print(f"  - 样本值: {sample.get('Value')}")
                    print(f"  - 样本时间: {sample.get('Date')}")

        except Exception as e:
            print(f"\n✗ API 调用失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_raw_api())
