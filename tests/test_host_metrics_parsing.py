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

            # 磁盘 IO (/proc/diskstats - 第一次采样)
            "cat /proc/diskstats | awk '{if($3 ~ /^(sd|vd|xvd|hd)[a-z]$/ || $3 ~ /^nvme[0-9]+n[0-9]+$/ || $3 ~ /^mmcblk[0-9]+$/) {reads+=$4; writes+=$8; read_sectors+=$6; write_sectors+=$10}} END {print reads, writes, read_sectors, write_sectors}'": "1000000 500000 20480000 10240000",

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
        # 磁盘 IO 需要两次采样，第二次返回增加的值
        if "cat /proc/diskstats" in command:
            count = self.call_count.get(command, 0)
            self.call_count[command] = count + 1
            if count == 0:
                # 第一次采样
                output = "1000000 500000 20480000 10240000"
            else:
                # 1秒后：读增加150次，写增加80次，读扇区增加4000个(2MB)，写扇区增加2000个(1MB)
                output = "1000150 500080 20484000 10242000"
        # 网络 IO 需要两次采样，第二次返回增加的值
        elif "cat /proc/net/dev" in command:
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

    # 磁盘 IO 指标（原始累计值）
    print("\n💾 磁盘 IO 指标（累计值）:")
    print(f"  ✓ 读操作总数: {metrics.get('disk_reads_total', 'N/A')}")
    print(f"  ✓ 写操作总数: {metrics.get('disk_writes_total', 'N/A')}")
    print(f"  ✓ 读取扇区总数: {metrics.get('disk_read_sectors_total', 'N/A')}")
    print(f"  ✓ 写入扇区总数: {metrics.get('disk_write_sectors_total', 'N/A')}")

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
        ("磁盘读操作总数", metrics.get('disk_reads_total') == 1000150),
        ("磁盘写操作总数", metrics.get('disk_writes_total') == 500080),
        ("磁盘读扇区总数", metrics.get('disk_read_sectors_total') == 20484000),
        ("磁盘写扇区总数", metrics.get('disk_write_sectors_total') == 10242000),
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
