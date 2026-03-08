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
    async def _get_linux_cpu_usage(ssh_client) -> Optional[float]:
        """获取 CPU 使用率"""
        try:
            # 使用 top 命令获取 CPU 使用率
            stdin, stdout, stderr = ssh_client.exec_command(
                "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
            )
            output = stdout.read().decode().strip()
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        # 备用方法：使用 mpstat
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                "mpstat 1 1 | awk '/Average/ {print 100 - $NF}'"
            )
            output = stdout.read().decode().strip()
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        return None

    @staticmethod
    async def _get_linux_memory_usage(ssh_client) -> Optional[float]:
        """获取内存使用率"""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                "free | grep Mem | awk '{print ($3/$2) * 100.0}'"
            )
            output = stdout.read().decode().strip()
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        return None

    @staticmethod
    async def _get_linux_disk_usage(ssh_client, mount_point: str = '/') -> Optional[float]:
        """获取磁盘使用率"""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                f"df -h {mount_point} | awk 'NR==2 {{print $5}}' | sed 's/%//'"
            )
            output = stdout.read().decode().strip()
            if output:
                return round(float(output), 2)
        except Exception:
            pass

        return None

    @staticmethod
    async def _get_linux_disk_io(ssh_client) -> Dict[str, float]:
        """获取磁盘 IO 统计"""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                "iostat -dx 1 2 | awk '/^[a-z]/ && NR>3 {reads+=$4; writes+=$5} END {print reads, writes}'"
            )
            output = stdout.read().decode().strip()
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
            # 读取网络接口统计
            stdin, stdout, stderr = ssh_client.exec_command(
                "cat /proc/net/dev | awk 'NR>2 {rx+=$2; tx+=$10} END {print rx, tx}'"
            )
            output = stdout.read().decode().strip()
            if output:
                parts = output.split()
                if len(parts) == 2:
                    return {
                        'network_rx_bytes': int(parts[0]),
                        'network_tx_bytes': int(parts[1])
                    }
        except Exception:
            pass

        return {}

    @staticmethod
    async def _get_linux_load_average(ssh_client) -> Dict[str, float]:
        """获取系统负载平均值"""
        try:
            stdin, stdout, stderr = ssh_client.exec_command("cat /proc/loadavg")
            output = stdout.read().decode().strip()
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
            # CPU 核心数
            stdin, stdout, stderr = ssh_client.exec_command("nproc")
            output = stdout.read().decode().strip()
            if output:
                info['cpu_cores'] = int(output)
        except Exception:
            pass

        try:
            # 总内存 (MB)
            stdin, stdout, stderr = ssh_client.exec_command(
                "free -m | grep Mem | awk '{print $2}'"
            )
            output = stdout.read().decode().strip()
            if output:
                info['total_memory_mb'] = int(output)
        except Exception:
            pass

        try:
            # 系统运行时间
            stdin, stdout, stderr = ssh_client.exec_command("uptime -s")
            output = stdout.read().decode().strip()
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
            # CPU 使用率
            stdin, stdout, stderr = ssh_client.exec_command(
                'powershell "Get-Counter \'\\Processor(_Total)\\% Processor Time\' | Select-Object -ExpandProperty CounterSamples | Select-Object -ExpandProperty CookedValue"'
            )
            output = stdout.read().decode().strip()
            if output:
                metrics['cpu_usage'] = round(float(output), 2)
        except Exception:
            pass

        try:
            # 内存使用率
            stdin, stdout, stderr = ssh_client.exec_command(
                'powershell "$os = Get-WmiObject Win32_OperatingSystem; [math]::Round((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize) * 100, 2)"'
            )
            output = stdout.read().decode().strip()
            if output:
                metrics['memory_usage'] = round(float(output), 2)
        except Exception:
            pass

        try:
            # 磁盘使用率
            stdin, stdout, stderr = ssh_client.exec_command(
                'powershell "Get-PSDrive C | Select-Object @{Name=\'UsedPercent\';Expression={[math]::Round(($_.Used / ($_.Used + $_.Free)) * 100, 2)}} | Select-Object -ExpandProperty UsedPercent"'
            )
            output = stdout.read().decode().strip()
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
