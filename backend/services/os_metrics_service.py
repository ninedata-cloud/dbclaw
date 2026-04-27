from typing import Any, Dict, Optional
from backend.services.ssh_service import SSHService


class OSMetricsService:
    """Collect OS-level metrics via SSH."""

    def __init__(self, ssh_service: SSHService):
        self.ssh = ssh_service

    def collect(self) -> Dict[str, Any]:
        commands = {
            "cpu": "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1 2>/dev/null || echo '0'",
            "memory": "free -b | awk 'NR==2{printf \"%d %d %d %d\", $2, $3, $4, $7}'",
            "disk": "df -B1 / | awk 'NR==2{printf \"%d %d %d %s\", $2, $3, $4, $5}'",
            "load": "cat /proc/loadavg 2>/dev/null || uptime | awk -F'load average:' '{print $2}'",
            "io": "iostat -d 1 1 2>/dev/null | awk 'NR==4{printf \"%s %s\", $3, $4}' || echo '0 0'",
            "net": "cat /proc/net/dev 2>/dev/null | awk 'NR>2{rx+=$2; tx+=$10} END{printf \"%d %d\", rx, tx}'",
            "uptime": "cat /proc/uptime 2>/dev/null | awk '{print $1}' || echo '0'",
        }

        results = self.ssh.execute_multi(list(commands.values()))

        metrics = {}
        outputs = list(results.values())

        # CPU
        try:
            metrics["cpu_usage"] = float(outputs[0].strip() or "0")
        except (ValueError, IndexError):
            metrics["cpu_usage"] = 0.0

        # Memory
        try:
            parts = outputs[1].strip().split()
            total = int(parts[0])
            used = int(parts[1])
            free = int(parts[2])
            available = int(parts[3]) if len(parts) > 3 else free
            metrics["memory_total_bytes"] = total
            metrics["memory_used_bytes"] = used
            metrics["memory_free_bytes"] = free
            metrics["memory_available_bytes"] = available
            metrics["memory_usage_percent"] = round(used / total * 100, 2) if total > 0 else 0
        except (ValueError, IndexError):
            metrics["memory_total_bytes"] = 0
            metrics["memory_used_bytes"] = 0
            metrics["memory_usage_percent"] = 0

        # Disk
        try:
            parts = outputs[2].strip().split()
            metrics["disk_total_bytes"] = int(parts[0])
            metrics["disk_used_bytes"] = int(parts[1])
            metrics["disk_free_bytes"] = int(parts[2])
            metrics["disk_usage_percent"] = float(parts[3].replace("%", "")) if len(parts) > 3 else 0
        except (ValueError, IndexError):
            metrics["disk_total_bytes"] = 0
            metrics["disk_used_bytes"] = 0
            metrics["disk_usage_percent"] = 0

        # Load average
        try:
            load_parts = outputs[3].strip().replace(",", " ").split()
            metrics["load_1m"] = float(load_parts[0])
            metrics["load_5m"] = float(load_parts[1])
            metrics["load_15m"] = float(load_parts[2])
        except (ValueError, IndexError):
            metrics["load_1m"] = 0
            metrics["load_5m"] = 0
            metrics["load_15m"] = 0

        # IO
        try:
            io_parts = outputs[4].strip().split()
            metrics["io_read_kb"] = float(io_parts[0]) if io_parts else 0
            metrics["io_write_kb"] = float(io_parts[1]) if len(io_parts) > 1 else 0
        except (ValueError, IndexError):
            metrics["io_read_kb"] = 0
            metrics["io_write_kb"] = 0

        # Network
        try:
            net_parts = outputs[5].strip().split()
            metrics["net_rx_bytes"] = int(net_parts[0]) if net_parts else 0
            metrics["net_tx_bytes"] = int(net_parts[1]) if len(net_parts) > 1 else 0
        except (ValueError, IndexError):
            metrics["net_rx_bytes"] = 0
            metrics["net_tx_bytes"] = 0

        # Uptime
        try:
            metrics["uptime_seconds"] = float(outputs[6].strip() or "0")
        except (ValueError, IndexError):
            metrics["uptime_seconds"] = 0

        return metrics
