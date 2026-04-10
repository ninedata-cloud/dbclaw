"""
OS Metrics Collector Service
操作系统指标采集服务 - 通过 SSH 采集 CPU、内存、磁盘等系统指标
"""
import asyncio
import re
from typing import Dict, Any, Optional
from datetime import datetime


class OSMetricsCollector:
    """OS 指标采集器"""

    @staticmethod
    async def collect_via_ssh(ssh_client, os_type: str = 'linux') -> Dict[str, Any]:
        """
        通过 SSH 采集操作系统指标

        Args:
            ssh_client: SSH 客户端连接
            os_type: 操作系统类型 (linux, windows)

        Returns:
            包含系统指标的字典
        """
        if os_type.lower() == 'linux':
            return await OSMetricsCollector._collect_linux_metrics(ssh_client)
        elif os_type.lower() == 'windows':
            return await OSMetricsCollector._collect_windows_metrics(ssh_client)
        else:
            return {}

    @staticmethod
    async def _collect_linux_metrics(ssh_client) -> Dict[str, Any]:
        """采集 Linux 系统指标"""
        metrics = {}

        try:
            # 1. CPU 使用率
            cpu_usage = await OSMetricsCollector._get_linux_cpu_usage(ssh_client)
            if cpu_usage is not None:
                metrics['cpu_usage'] = cpu_usage

            # 2. 内存使用率
            memory_stats = await OSMetricsCollector._get_linux_memory_stats(ssh_client)
            if memory_stats:
                metrics.update(memory_stats)
            else:
                memory_usage = await OSMetricsCollector._get_linux_memory_usage(ssh_client)
                if memory_usage is not None:
                    metrics['memory_usage'] = memory_usage

            # 3. 磁盘使用率
            disk_usage = await OSMetricsCollector._get_linux_disk_usage(ssh_client)
            if disk_usage is not None:
                metrics['disk_usage'] = disk_usage

            # 4. 磁盘 IO
            disk_io = await OSMetricsCollector._get_linux_disk_io(ssh_client)
            if disk_io:
                metrics.update(disk_io)

            # 5. 网络 IO
            network_io = await OSMetricsCollector._get_linux_network_io(ssh_client)
            if network_io:
                metrics.update(network_io)

            # 6. 负载平均值
            load_avg = await OSMetricsCollector._get_linux_load_average(ssh_client)
            if load_avg:
                metrics.update(load_avg)

            # 7. 系统信息
            system_info = await OSMetricsCollector._get_linux_system_info(ssh_client)
            if system_info:
                metrics.update(system_info)

        except Exception as e:
            metrics['error'] = str(e)

        return metrics

    @staticmethod
    async def _exec(ssh_client, command: str) -> str:
        """在线程池中执行 SSH 命令，避免阻塞事件循环"""
        import asyncio
        loop = asyncio.get_event_loop()
        def _run():
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=15)
            return stdout.read().decode().strip()
        return await loop.run_in_executor(None, _run)

    @staticmethod
    async def _get_linux_cpu_usage(ssh_client) -> Optional[float]:
        """获取 CPU 使用率"""
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
            )
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        # 备用方法：使用 mpstat
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                "mpstat 1 1 | awk '/Average/ {print 100 - $NF}'"
            )
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        return None

    @staticmethod
    async def _get_linux_memory_usage(ssh_client) -> Optional[float]:
        """获取内存使用率"""
        try:
            memory_stats = await OSMetricsCollector._get_linux_memory_stats(ssh_client)
            usage = memory_stats.get('memory_usage')
            if usage is not None:
                return round(float(usage), 2)
        except Exception:
            pass

        # 备用方法：使用 free 命令，兼容较老或极简系统
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                "free | awk '/^Mem:/ {print ($3/$2) * 100.0}'"
            )
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        return None

    @staticmethod
    async def _get_linux_memory_stats(ssh_client) -> Dict[str, float]:
        """从 /proc/meminfo 获取更可靠的内存统计，兼容老内核。

        `memory_usage` 采用 `(MemTotal - MemAvailable) / MemTotal` 口径，更贴近
        Linux 的真实可用内存压力。
        """
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                "cat /proc/meminfo"
            )
        except Exception:
            return {}

        if not output:
            return {}

        meminfo: Dict[str, int] = {}
        for line in output.splitlines():
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            key = parts[0].strip()
            match = re.search(r"(\d+)", parts[1])
            if not match:
                continue
            meminfo[key] = int(match.group(1))

        total_kb = meminfo.get("MemTotal")
        if not total_kb:
            return {}

        free_kb = meminfo.get("MemFree", 0)
        reclaimable_cache_kb = (
            meminfo.get("Buffers", 0)
            + meminfo.get("Cached", 0)
            + meminfo.get("SReclaimable", 0)
            - meminfo.get("Shmem", 0)
        )
        reclaimable_cache_kb = max(reclaimable_cache_kb, 0)

        available_kb = meminfo.get("MemAvailable")
        if available_kb is None:
            # 老内核没有 MemAvailable，按 kernel 文档近似估算可用内存
            available_kb = (
                free_kb
                + meminfo.get("Buffers", 0)
                + meminfo.get("Cached", 0)
                + meminfo.get("SReclaimable", 0)
                - meminfo.get("Shmem", 0)
            )

        available_kb = max(0, min(available_kb, total_kb))
        pressure_used_kb = max(total_kb - available_kb, 0)
        pressure_usage = round((pressure_used_kb / total_kb) * 100, 2)

        return {
            "memory_total_kb": float(total_kb),
            "memory_free_kb": float(free_kb),
            "memory_reclaimable_cache_kb": float(reclaimable_cache_kb),
            "memory_available_kb": float(available_kb),
            "memory_used_kb": float(pressure_used_kb),
            "memory_pressure_used_kb": float(pressure_used_kb),
            "memory_usage": pressure_usage,
            "memory_pressure_usage": pressure_usage,
        }

    @staticmethod
    async def _get_linux_disk_usage(ssh_client, mount_point: str = '/') -> Optional[float]:
        """获取磁盘使用率"""
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                f"df -h {mount_point} | awk 'NR==2 {{print $5}}' | sed 's/%//'"
            )
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        return None

    @staticmethod
    async def _get_linux_disk_io(ssh_client) -> Dict[str, float]:
        """获取磁盘 IO 统计"""
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                "iostat -dx 1 2 | awk '/^[a-z]/ && NR>3 {reads+=$4; writes+=$5} END {print reads, writes}'"
            )
            if output:
                parts = output.split()
                if len(parts) == 2:
                    return {
                        'disk_reads_per_sec': round(float(parts[0]), 2),
                        'disk_writes_per_sec': round(float(parts[1]), 2)
                    }
        except Exception:
            pass

        return {}

    @staticmethod
    async def _get_linux_network_io(ssh_client) -> Dict[str, float]:
        """获取网络 IO 统计"""
        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                "cat /proc/net/dev | awk 'NR>2 {rx+=$2; tx+=$10} END {print rx, tx}'"
            )
            if output:
                parts = output.split()
                if len(parts) == 2:
                    return {
                        'host_network_rx_bytes': int(parts[0]),
                        'host_network_tx_bytes': int(parts[1])
                    }
        except Exception:
            pass

        return {}

    @staticmethod
    async def _get_linux_load_average(ssh_client) -> Dict[str, float]:
        """获取系统负载平均值"""
        try:
            output = await OSMetricsCollector._exec(ssh_client, "cat /proc/loadavg")
            if output:
                parts = output.split()
                if len(parts) >= 3:
                    return {
                        'load_avg_1min': round(float(parts[0]), 2),
                        'load_avg_5min': round(float(parts[1]), 2),
                        'load_avg_15min': round(float(parts[2]), 2)
                    }
        except Exception:
            pass

        return {}

    @staticmethod
    async def _get_linux_system_info(ssh_client) -> Dict[str, Any]:
        """获取系统信息"""
        info = {}

        try:
            output = await OSMetricsCollector._exec(ssh_client, "nproc")
            if output:
                info['cpu_cores'] = int(output)
        except Exception:
            pass

        try:
            memory_stats = await OSMetricsCollector._get_linux_memory_stats(ssh_client)
            total_memory_kb = memory_stats.get('memory_total_kb')
            if total_memory_kb is not None:
                info['total_memory_mb'] = int(round(total_memory_kb / 1024))
        except Exception:
            pass

        if 'total_memory_mb' not in info:
            try:
                output = await OSMetricsCollector._exec(
                    ssh_client,
                    "free -m | awk '/^Mem:/ {print $2}'"
                )
                if output:
                    info['total_memory_mb'] = int(output)
            except Exception:
                pass

        try:
            output = await OSMetricsCollector._exec(ssh_client, "uptime -s")
            if output:
                info['boot_time'] = output
        except Exception:
            pass

        return info

    @staticmethod
    async def _collect_windows_metrics(ssh_client) -> Dict[str, Any]:
        """采集 Windows 系统指标（通过 PowerShell）"""
        metrics = {}

        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                'powershell "Get-Counter \'\\Processor(_Total)\\% Processor Time\' | Select-Object -ExpandProperty CounterSamples | Select-Object -ExpandProperty CookedValue"'
            )
            if output:
                metrics['cpu_usage'] = round(float(output), 2)
        except Exception:
            pass

        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                'powershell "$os = Get-WmiObject Win32_OperatingSystem; [math]::Round((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize) * 100, 2)"'
            )
            if output:
                metrics['memory_usage'] = round(float(output), 2)
        except Exception:
            pass

        try:
            output = await OSMetricsCollector._exec(
                ssh_client,
                'powershell "Get-PSDrive C | Select-Object @{Name=\'UsedPercent\';Expression={[math]::Round(($_.Used / ($_.Used + $_.Free)) * 100, 2)}} | Select-Object -ExpandProperty UsedPercent"'
            )
            if output:
                metrics['disk_usage'] = round(float(output), 2)
        except Exception:
            pass

        return metrics

    @staticmethod
    def calculate_cpu_load_percent(load_avg: float, cpu_cores: int) -> float:
        """
        将负载平均值转换为 CPU 负载百分比

        Args:
            load_avg: 负载平均值
            cpu_cores: CPU 核心数

        Returns:
            CPU 负载百分比
        """
        if cpu_cores <= 0:
            return 0.0
        return round((load_avg / cpu_cores) * 100, 2)
