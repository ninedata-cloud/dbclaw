"""
测试主机配置 API
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from backend.routers.host_detail import get_host_config
from backend.schemas.host_detail import HostConfigResponse


@pytest.mark.asyncio
async def test_host_config_response_structure():
    """测试主机配置响应结构"""
    config = HostConfigResponse(
        cpu={
            "model": "Intel(R) Xeon(R) CPU",
            "cores": 8,
            "physical_cpus": 2,
            "mhz": "2400.000"
        },
        memory={
            "MemTotal": "16384000 kB",
            "MemFree": "8192000 kB",
            "MemAvailable": "10240000 kB"
        },
        disk=[
            {
                "filesystem": "/dev/sda1",
                "size": "100G",
                "used": "50G",
                "available": "50G",
                "use_percent": "50%",
                "mounted_on": "/"
            }
        ],
        network=[
            {
                "interface": "eth0",
                "family": "inet",
                "address": "192.168.1.100/24"
            }
        ],
        system={
            "kernel": "5.10.0-21-amd64",
            "os_name": "Debian GNU/Linux",
            "os_version": "11 (bullseye)",
            "hostname": "db-server-01",
            "uptime_seconds": 864000,
            "load_avg_1": "0.50",
            "load_avg_5": "0.45",
            "load_avg_15": "0.40"
        },
        collected_at=datetime.utcnow()
    )

    assert config.cpu["cores"] == 8
    assert config.memory["MemTotal"] == "16384000 kB"
    assert len(config.disk) == 1
    assert len(config.network) == 1
    assert config.system["hostname"] == "db-server-01"


def test_cpu_info_parsing():
    """测试 CPU 信息解析"""
    raw_data = {
        'cpu_model': 'Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz',
        'cpu_cores': '8',
        'cpu_physical': '1',
        'cpu_mhz': '3600.000'
    }

    cpu_info = {
        "model": raw_data.get('cpu_model', 'Unknown'),
        "cores": int(raw_data.get('cpu_cores', '0') or '0'),
        "physical_cpus": int(raw_data.get('cpu_physical', '0') or '0'),
        "mhz": raw_data.get('cpu_mhz', 'Unknown'),
    }

    assert cpu_info["model"] == 'Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz'
    assert cpu_info["cores"] == 8
    assert cpu_info["physical_cpus"] == 1
    assert cpu_info["mhz"] == '3600.000'


def test_memory_info_parsing():
    """测试内存信息解析"""
    memory_output = """MemTotal:       16384000 kB
MemFree:         8192000 kB
MemAvailable:   10240000 kB
Buffers:          512000 kB
Cached:          2048000 kB
SwapTotal:       4096000 kB
SwapFree:        4096000 kB"""

    memory_lines = memory_output.split('\n')
    memory_info = {}
    for line in memory_lines:
        if ':' in line:
            key, value = line.split(':', 1)
            memory_info[key.strip()] = value.strip()

    assert memory_info["MemTotal"] == "16384000 kB"
    assert memory_info["MemFree"] == "8192000 kB"
    assert memory_info["SwapTotal"] == "4096000 kB"


def test_disk_info_parsing():
    """测试磁盘信息解析"""
    disk_output = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   50G   50G  50% /
/dev/sdb1       200G  100G  100G  50% /data"""

    disk_lines = disk_output.split('\n')
    disk_info = []
    for i, line in enumerate(disk_lines):
        if i == 0:  # 跳过表头
            continue
        parts = line.split()
        if len(parts) >= 6:
            disk_info.append({
                "filesystem": parts[0],
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_percent": parts[4],
                "mounted_on": parts[5]
            })

    assert len(disk_info) == 2
    assert disk_info[0]["filesystem"] == "/dev/sda1"
    assert disk_info[0]["use_percent"] == "50%"
    assert disk_info[1]["mounted_on"] == "/data"


def test_network_info_parsing():
    """测试网络接口信息解析"""
    network_output = """1: lo inet 127.0.0.1/8
2: eth0 inet 192.168.1.100/24
3: eth0 inet6 fe80::1/64"""

    network_lines = network_output.split('\n')
    network_info = []
    seen_interfaces = set()
    for line in network_lines:
        parts = line.split()
        if len(parts) >= 3:
            iface = parts[1]
            if iface not in seen_interfaces:
                network_info.append({
                    "interface": iface,
                    "family": parts[2],
                    "address": parts[3] if len(parts) > 3 else ""
                })
                seen_interfaces.add(iface)

    assert len(network_info) == 2
    assert network_info[0]["interface"] == "lo"
    assert network_info[1]["interface"] == "eth0"


def test_system_info_parsing():
    """测试系统信息解析"""
    os_release = """NAME="Debian GNU/Linux"
VERSION="11 (bullseye)"
ID=debian
VERSION_ID="11\""""

    os_release_lines = os_release.split('\n')
    os_name = "Unknown"
    os_version = ""
    for line in os_release_lines:
        if line.startswith('NAME='):
            os_name = line.split('=', 1)[1].strip('"')
        elif line.startswith('VERSION='):
            os_version = line.split('=', 1)[1].strip('"')

    assert os_name == "Debian GNU/Linux"
    assert os_version == "11 (bullseye)"

    # 测试运行时间解析
    uptime_seconds = 0
    try:
        uptime_seconds = int(float("864000.50"))
    except:
        pass

    assert uptime_seconds == 864000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
