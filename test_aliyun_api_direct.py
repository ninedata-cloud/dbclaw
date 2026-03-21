#!/usr/bin/env python3
"""
直接测试阿里云 API 调用
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.system_config import SystemConfig
from sqlalchemy import select
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta
import aiohttp


async def test_aliyun_api_directly():
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
        region_id = "cn-hangzhou"
        instance_id = "rm-bp16knn4mo4fvh99i"

        print(f"测试参数:")
        print(f"  - Region: {region_id}")
        print(f"  - Instance ID: {instance_id}")
        print(f"  - AccessKey ID: {access_key_id[:10]}...")

        # 时间范围 - 查询过去 2 小时到 1 小时前的数据
        now = datetime.utcnow().replace(second=0, microsecond=0)
        end_time = (now - timedelta(hours=1))
        start_time = (now - timedelta(hours=2))

        # Timestamp 应该是当前时间
        timestamp_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"\n时间参数:")
        print(f"  - Timestamp (当前时间): {timestamp_str}")
        print(f"  - StartTime: {start_time_str}")
        print(f"  - EndTime: {end_time_str}")

        # 构建请求参数
        common_params = {
            "Format": "JSON",
            "Version": "2014-08-15",
            "AccessKeyId": access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": timestamp_str,  # 使用当前时间
            "SignatureVersion": "1.0",
            "SignatureNonce": str(int(time.time() * 1000)),
            "Action": "DescribeDBInstancePerformance",
            "DBInstanceId": instance_id,
            "Key": "MySQL_NetworkTraffic",
            "StartTime": start_time_str,
            "EndTime": end_time_str
        }

        # 签名
        sorted_params = sorted(common_params.items())
        query_string = "&".join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted_params])
        string_to_sign = f"GET&%2F&{urllib.parse.quote(query_string, safe='')}"
        signature = base64.b64encode(hmac.new(
            (access_key_secret + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1
        ).digest()).decode("utf-8")

        common_params["Signature"] = signature

        # 发送请求
        url = f"https://rds.{region_id}.aliyuncs.com/"

        print(f"\n发送请求到: {url}")
        print(f"参数数量: {len(common_params)}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=common_params) as response:
                status = response.status
                text = await response.text()

                print(f"\n响应:")
                print(f"  - Status: {status}")
                print(f"  - Body: {text[:500]}")

                if status == 200:
                    print(f"\n✓ API 调用成功")
                else:
                    print(f"\n✗ API 调用失败")


if __name__ == "__main__":
    asyncio.run(test_aliyun_api_directly())
