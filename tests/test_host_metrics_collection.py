"""测试主机指标采集功能"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.os_metrics_collector import OSMetricsCollector
from backend.services.ssh_connection_pool import SSHConnectionPool
from backend.database import async_session
from backend.models.host import Host
from sqlalchemy import select


async def test_metrics_collection():
    """测试指标采集"""
    print("=" * 60)
    print("测试主机指标采集")
    print("=" * 60)

    async with async_session() as db:
        # 获取第一个主机
        result = await db.execute(select(Host).limit(1))
        host = result.scalar_one_or_none()

        if not host:
            print("❌ 没有找到主机，请先添加主机")
            return

        print(f"\n📡 测试主机: {host.name} ({host.host}:{host.port})")
        print("-" * 60)

        try:
            # 创建 SSH 连接池
            ssh_pool = SSHConnectionPool()

            # 获取 SSH 连接
            async with ssh_pool.get_connection(db, host.id) as ssh_client:
                print("✅ SSH 连接成功")

                # 采集指标
                print("\n🔍 开始采集指标...")
                metrics = await OSMetricsCollector.collect_via_ssh(ssh_client, os_type='linux')

                print("\n📊 采集到的指标:")
                print("-" * 60)

                # 基础指标
                print(f"CPU 使用率: {metrics.get('cpu_usage', 'N/A')}%")
                print(f"内存使用率: {metrics.get('memory_usage', 'N/A')}%")
                print(f"磁盘使用率: {metrics.get('disk_usage', 'N/A')}%")

                # 磁盘 IO 指标（原始累计值）
                print("\n💾 磁盘 IO 指标（累计值）:")
                print(f"  读操作总数: {metrics.get('disk_reads_total', 'N/A')}")
                print(f"  写操作总数: {metrics.get('disk_writes_total', 'N/A')}")
                print(f"  读取扇区总数: {metrics.get('disk_read_sectors_total', 'N/A')}")
                print(f"  写入扇区总数: {metrics.get('disk_write_sectors_total', 'N/A')}")
                if metrics.get('disk_read_sectors_total'):
                    read_kb = metrics['disk_read_sectors_total'] * 512 / 1024
                    print(f"  读取总量: {read_kb:.2f} KB")
                if metrics.get('disk_write_sectors_total'):
                    write_kb = metrics['disk_write_sectors_total'] * 512 / 1024
                    print(f"  写入总量: {write_kb:.2f} KB")

                # 网络 IO 指标
                print("\n🌐 网络 IO 指标:")
                print(f"  接收总量: {metrics.get('network_rx_bytes_total', 'N/A')} bytes")
                print(f"  发送总量: {metrics.get('network_tx_bytes_total', 'N/A')} bytes")
                print(f"  接收速率: {metrics.get('network_rx_kb_per_sec', 'N/A')} KB/s")
                print(f"  发送速率: {metrics.get('network_tx_kb_per_sec', 'N/A')} KB/s")

                # 负载指标
                print("\n📈 系统负载:")
                print(f"  1分钟: {metrics.get('load_avg_1min', 'N/A')}")
                print(f"  5分钟: {metrics.get('load_avg_5min', 'N/A')}")
                print(f"  15分钟: {metrics.get('load_avg_15min', 'N/A')}")

                # 系统信息
                print("\n💻 系统信息:")
                print(f"  CPU 核心数: {metrics.get('cpu_cores', 'N/A')}")
                print(f"  总内存: {metrics.get('total_memory_mb', 'N/A')} MB")

                if metrics.get('error'):
                    print(f"\n⚠️  采集过程中出现错误: {metrics['error']}")
                else:
                    print("\n✅ 指标采集成功!")

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_metrics_collection())
