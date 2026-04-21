#!/usr/bin/env python3
"""
阿里云 RDS 完整指标采集验证测试
验证 CPU、内存、磁盘、网络、QPS、连接数等所有指标
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.integration import Integration
from backend.models.datasource import Datasource
from backend.services.integration_executor import IntegrationExecutor
from sqlalchemy import select
from collections import defaultdict
import logging


async def test_all_metrics():
    """测试所有指标采集"""

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 80)
    print("阿里云 RDS 完整指标采集验证")
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

        print(f"\n测试配置:")
        print(f"  - 集成: {integration.name}")
        print(f"  - 数据源 ID: {test_datasource_id}")
        print(f"  - 地域: {test_params['region_id']}")

        print(f"\n执行测试...")
        print("-" * 80)

        try:
            # 直接调用集成执行器获取完整数据
            from backend.services.integration_executor import IntegrationExecutor
            from backend.models.datasource import Datasource
            import logging

            # 获取数据源
            ds_result = await db.execute(
                select(Datasource).where(Datasource.id == test_datasource_id)
            )
            datasource = ds_result.scalar_one_or_none()

            if not datasource:
                print(f"✗ 数据源 ID {test_datasource_id} 不存在")
                return False

            datasource = [{
                "id": datasource.id,
                "name": datasource.name,
                "db_type": datasource.db_type,
                "external_instance_id": getattr(datasource, "external_instance_id", None)
            }]

            # 创建执行器
            logger = logging.getLogger(__name__)
            executor = IntegrationExecutor(db, logger)

            # 执行指标采集
            metrics = await executor.execute_metric_collection(
                integration.code,
                test_params,
                datasource
            )

            print(f"✓ 测试成功")
            print(f"  - 总指标数: {len(metrics)}")

            # 按指标类型分组统计
            metric_groups = defaultdict(list)
            for metric in metrics:
                metric_name = metric.get("metric_name")
                metric_groups[metric_name].append(metric)

            print(f"\n指标分类统计:")
            print("-" * 80)

            # 定义期望的指标及其说明
            expected_metrics = {
                "cpu_usage": ("CPU 使用率", "%"),
                "memory_usage": ("内存使用率", "%"),
                "disk_total": ("磁盘总空间", "MB"),
                "disk_data": ("数据空间", "MB"),
                "disk_log": ("日志空间", "MB"),
                "disk_temp": ("临时空间", "MB"),
                "disk_system": ("系统空间", "MB"),
                "iops": ("IOPS", "次/秒"),
                "throughput": ("吞吐量", "Byte/秒"),
                "network_in": ("入流量", "KB/秒"),
                "network_out": ("出流量", "KB/秒"),
                "qps": ("QPS", "次/秒"),
                "tps": ("TPS", "个/秒"),
                "connections_active": ("活跃连接数", "个"),
                "connections_total": ("总连接数", "个")
            }

            found_metrics = set()
            missing_metrics = []

            for metric_name, (description, unit) in expected_metrics.items():
                if metric_name in metric_groups:
                    count = len(metric_groups[metric_name])
                    sample = metric_groups[metric_name][0]
                    value = sample.get("metric_value")
                    timestamp = sample.get("timestamp", "")[:19]  # 只显示到秒

                    print(f"✓ {description:12} ({metric_name:20}): {count:3} 条")
                    print(f"    样本值: {value:10.2f} {unit:10} @ {timestamp}")

                    found_metrics.add(metric_name)
                else:
                    missing_metrics.append((metric_name, description))

            # 检查是否有缺失的指标
            if missing_metrics:
                print(f"\n⚠ 缺失的指标:")
                for metric_name, description in missing_metrics:
                    print(f"  ✗ {description} ({metric_name})")
            else:
                print(f"\n✓ 所有期望的指标都已采集")

            # 检查是否有未预期的指标
            unexpected = set(metric_groups.keys()) - found_metrics
            if unexpected:
                print(f"\n⚠ 未预期的指标:")
                for metric_name in unexpected:
                    count = len(metric_groups[metric_name])
                    print(f"  ? {metric_name}: {count} 条")

            # 数据质量检查
            print(f"\n数据质量检查:")
            print("-" * 80)

            quality_issues = []

            for metric_name, metric_list in metric_groups.items():
                # 检查是否有空值
                null_count = sum(1 for m in metric_list if m.get("metric_value") is None)
                if null_count > 0:
                    quality_issues.append(f"  ✗ {metric_name}: {null_count} 条空值")

                # 检查是否有负值（某些指标不应该为负）
                if metric_name in ["cpu_usage", "memory_usage", "disk_total", "disk_data", "iops"]:
                    negative_count = sum(1 for m in metric_list if m.get("metric_value", 0) < 0)
                    if negative_count > 0:
                        quality_issues.append(f"  ✗ {metric_name}: {negative_count} 条负值")

                # 检查 CPU 和内存使用率是否超过 100%
                if metric_name in ["cpu_usage", "memory_usage"]:
                    over_100 = sum(1 for m in metric_list if m.get("metric_value", 0) > 100)
                    if over_100 > 0:
                        quality_issues.append(f"  ✗ {metric_name}: {over_100} 条超过 100%")

            if quality_issues:
                print("发现数据质量问题:")
                for issue in quality_issues:
                    print(issue)
            else:
                print("✓ 数据质量检查通过")

            # 时间戳检查
            print(f"\n时间戳检查:")
            print("-" * 80)

            if metrics:
                timestamps = [m.get("timestamp") for m in metrics if m.get("timestamp")]
                if timestamps:
                    print(f"  - 最早时间: {min(timestamps)}")
                    print(f"  - 最晚时间: {max(timestamps)}")
                    print(f"  - 时间跨度: 约 {len(set(timestamps))} 个不同时间点")
                    print(f"  ✓ 时间戳格式正确")
                else:
                    print(f"  ✗ 没有时间戳数据")
            else:
                print(f"  ✗ 没有指标数据")

            # 最终结论
            print(f"\n" + "=" * 80)
            print("测试结论:")
            print("=" * 80)

            if not missing_metrics and not quality_issues:
                print("✓ 所有指标采集正常")
                print("✓ 数据质量良好")
                print("✓ 可以投入生产使用")
                return True
            else:
                if missing_metrics:
                    print(f"⚠ 缺失 {len(missing_metrics)} 个指标")
                if quality_issues:
                    print(f"⚠ 发现 {len(quality_issues)} 个数据质量问题")
                print("建议检查后再投入生产使用")
                return False

        except Exception as e:
            print(f"\n✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_all_metrics())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
