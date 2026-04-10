import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.os_metrics_collector import OSMetricsCollector


@pytest.mark.asyncio
async def test_linux_memory_usage_uses_memavailable_formula(monkeypatch):
    meminfo_output = """MemTotal:       16384000 kB
MemFree:         1024000 kB
MemAvailable:    4096000 kB
Buffers:          256000 kB
Cached:          4096000 kB
SReclaimable:     512000 kB
Shmem:            256000 kB
"""

    async def fake_exec(_ssh_client, command: str) -> str:
        if command == "cat /proc/meminfo":
            return meminfo_output
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(OSMetricsCollector, "_exec", fake_exec)

    stats = await OSMetricsCollector._get_linux_memory_stats(object())
    usage = await OSMetricsCollector._get_linux_memory_usage(object())
    system_info = await OSMetricsCollector._get_linux_system_info(object())

    assert usage == 75.0
    assert stats["memory_usage"] == 75.0
    assert stats["memory_pressure_usage"] == 75.0
    assert "memory_working_set_usage" not in stats
    assert system_info["total_memory_mb"] == 16000


@pytest.mark.asyncio
async def test_linux_memory_usage_falls_back_when_memavailable_missing(monkeypatch):
    meminfo_output = """MemTotal:        8000000 kB
MemFree:          500000 kB
Buffers:          250000 kB
Cached:          2000000 kB
SReclaimable:     300000 kB
Shmem:            100000 kB
"""

    async def fake_exec(_ssh_client, command: str) -> str:
        if command == "cat /proc/meminfo":
            return meminfo_output
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(OSMetricsCollector, "_exec", fake_exec)

    stats = await OSMetricsCollector._get_linux_memory_stats(object())
    usage = await OSMetricsCollector._get_linux_memory_usage(object())

    expected_available = 500000 + 250000 + 2000000 + 300000 - 100000
    expected_usage = round((8000000 - expected_available) / 8000000 * 100, 2)
    assert math.isclose(usage, expected_usage, rel_tol=0, abs_tol=0.01)
    assert math.isclose(stats["memory_pressure_usage"], expected_usage, rel_tol=0, abs_tol=0.01)
    assert "memory_working_set_usage" not in stats


@pytest.mark.asyncio
async def test_linux_memory_usage_falls_back_to_free_when_meminfo_unavailable(monkeypatch):
    async def fake_exec(_ssh_client, command: str) -> str:
        if command == "cat /proc/meminfo":
            return ""
        if command == "free | awk '/^Mem:/ {print ($3/$2) * 100.0}'":
            return "73.26"
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(OSMetricsCollector, "_exec", fake_exec)

    usage = await OSMetricsCollector._get_linux_memory_usage(object())

    assert usage == 73.26
