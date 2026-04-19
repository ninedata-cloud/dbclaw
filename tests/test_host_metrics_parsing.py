"""测试主机指标解析逻辑"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockSSHClient:
    """模拟 SSH 客户端"""

    def __init__(self):
        self.commands = {
            # CPU
            "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'": "25.5",

            # 内存
            "cat /proc/meminfo": """MemTotal:       16384000 kB
MemFree:         4096000 kB
MemAvailable:    8192000 kB
Buffers:          512000 kB
Cached:          3072000 kB
SReclaimable:     256000 kB
Shmem:            128000 kB
SwapTotal:       2048000 kB
SwapFree:        1024000 kB""",

            # 磁盘使用率
            "df -h / | awk 'NR==2 {print $5}' | sed 's/%//'": "45",

            # 磁盘 IO (iostat)
            "iostat -dx 1 2 | awk '/^[a-z]/ && NR>3 {r+=$4; w+=$5; rkb+=$6; wkb+=$7} END {print r, w, rkb, wkb}'": "150.5 80.2 2048.5 1024.3",

            # 网络 IO (第一次采样)
            "cat /proc/net/dev | awk 'NR>2 && $1 !~ /^lo:/ {rx+=$2; tx+=$10} END {print rx, tx}'": "1000000000 500000000",

            # 负载
            "cat /proc/loadavg": "1.5 2.0 2.5 2/500 12345",

            # CPU 核心数
            "nproc": "8",

            # 启动时间
            "uptime -s": "2026-04-18 10:30:00",
        }
        self.call_count = {}

    def exec_command(self, command, timeout=15):
        """模拟执行命令"""
        # 网络 IO 需要两次采样，第二次返回增加的值
        if "cat /proc/net/dev" in command:
            count = self.call_count.get(command, 0)
            self.call_count[command] = count + 1
            if count == 0:
                output = "1000000000 500000000"
            else:
                # 1秒后增加了 1MB 接收，512KB 发送
                output = "1001048576 500524288"
        else:
            output = self.commands.get(command, "")

        class MockStdout:
            def __init__(self, data):
                self.data = data
            def read(self):
                return self.data.encode()

        return None, MockStdout(output), None


async def test_metrics_parsing():
    """测试指标解析"""
    from backend.services.os_metrics_collector import OSMetricsCollector

    print("=" * 60)
    print("测试主机指标解析逻辑")
    print("=" * 60)

    mock_client = MockSSHClient()

    print("\n🔍 开始采集指标...")
    metrics = await OSMetricsCollector.collect_via_ssh(mock_client, os_type='linux')

    print("\n📊 采集到的指标:")
    print("-" * 60)

    # 基础指标
    print(f"✓ CPU 使用率: {metrics.get('cpu_usage', 'N/A')}%")
    print(f"✓ 内存使用率: {metrics.get('memory_usage', 'N/A')}%")
    print(f"✓ 磁盘使用率: {metrics.get('disk_usage', 'N/A')}%")

    # 磁盘 IO 指标
    print("\n💾 磁盘 IO 指标:")
    print(f"  ✓ 读 IOPS: {metrics.get('disk_read_iops', 'N/A')}")
    print(f"  ✓ 写 IOPS: {metrics.get('disk_write_iops', 'N/A')}")
    print(f"  ✓ 读取速率: {metrics.get('disk_read_kb_per_sec', 'N/A')} KB/s")
    print(f"  ✓ 写入速率: {metrics.get('disk_write_kb_per_sec', 'N/A')} KB/s")

    # 网络 IO 指标
    print("\n🌐 网络 IO 指标:")
    print(f"  ✓ 接收总量: {metrics.get('network_rx_bytes_total', 'N/A')} bytes")
    print(f"  ✓ 发送总量: {metrics.get('network_tx_bytes_total', 'N/A')} bytes")
    print(f"  ✓ 接收速率: {metrics.get('network_rx_bytes_per_sec', 'N/A')} bytes/s")
    print(f"  ✓ 发送速率: {metrics.get('network_tx_bytes_per_sec', 'N/A')} bytes/s")
    print(f"  ✓ 接收速率: {metrics.get('network_rx_kb_per_sec', 'N/A')} KB/s")
    print(f"  ✓ 发送速率: {metrics.get('network_tx_kb_per_sec', 'N/A')} KB/s")

    # 负载指标
    print("\n📈 系统负载:")
    print(f"  ✓ 1分钟: {metrics.get('load_avg_1min', 'N/A')}")
    print(f"  ✓ 5分钟: {metrics.get('load_avg_5min', 'N/A')}")
    print(f"  ✓ 15分钟: {metrics.get('load_avg_15min', 'N/A')}")

    # 系统信息
    print("\n💻 系统信息:")
    print(f"  ✓ CPU 核心数: {metrics.get('cpu_cores', 'N/A')}")
    print(f"  ✓ 总内存: {metrics.get('total_memory_mb', 'N/A')} MB")
    print(f"  ✓ 启动时间: {metrics.get('boot_time', 'N/A')}")

    # 验证关键指标
    print("\n" + "=" * 60)
    print("验证结果:")
    print("-" * 60)

    checks = [
        ("CPU 使用率", metrics.get('cpu_usage') == 25.5),
        ("内存使用率", metrics.get('memory_usage') is not None),
        ("磁盘使用率", metrics.get('disk_usage') == 45.0),
        ("磁盘读 IOPS", metrics.get('disk_read_iops') == 150.5),
        ("磁盘写 IOPS", metrics.get('disk_write_iops') == 80.2),
        ("磁盘读速率", metrics.get('disk_read_kb_per_sec') == 2048.5),
        ("磁盘写速率", metrics.get('disk_write_kb_per_sec') == 1024.3),
        ("网络接收速率", metrics.get('network_rx_kb_per_sec') == 1024.0),
        ("网络发送速率", metrics.get('network_tx_kb_per_sec') == 512.0),
        ("负载 1分钟", metrics.get('load_avg_1min') == 1.5),
        ("CPU 核心数", metrics.get('cpu_cores') == 8),
    ]

    passed = sum(1 for _, result in checks if result)
    total = len(checks)

    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {name}")

    print("-" * 60)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过!")
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        print("\n完整指标数据:")
        import json
        print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(test_metrics_parsing())
