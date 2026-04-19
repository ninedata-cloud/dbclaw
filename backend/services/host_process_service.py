import asyncio
import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class HostProcessService:
    """主机进程采集服务"""

    @staticmethod
    async def get_processes(ssh_client) -> List[Dict[str, Any]]:
        """通过 SSH 获取进程列表"""
        try:
            loop = asyncio.get_event_loop()

            def _run():
                stdin, stdout, stderr = ssh_client.exec_command(
                    "ps aux --sort=-%cpu | head -50",
                    timeout=10
                )
                return stdout.read().decode('utf-8', errors='replace')

            output = await loop.run_in_executor(None, _run)
            return HostProcessService._parse_ps_output(output)
        except Exception as e:
            logger.error(f"Failed to get processes: {e}")
            return []

    @staticmethod
    def _parse_ps_output(output: str) -> List[Dict[str, Any]]:
        """解析 ps aux 输出"""
        processes = []
        lines = output.strip().split('\n')

        if len(lines) < 2:
            return processes

        # 跳过表头
        for line in lines[1:]:
            try:
                # ps aux 格式: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({
                        'user': parts[0],
                        'pid': int(parts[1]),
                        'cpu_percent': float(parts[2]),
                        'memory_percent': float(parts[3]),
                        'state': parts[7],
                        'start_time': parts[8],
                        'command': parts[10][:200]  # 限制命令长度
                    })
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse process line: {line[:50]}... Error: {e}")
                continue

        return processes

    @staticmethod
    async def kill_process(ssh_client, pid: int) -> bool:
        """终止进程"""
        try:
            loop = asyncio.get_event_loop()

            def _run():
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"kill -9 {pid}",
                    timeout=5
                )
                exit_status = stdout.channel.recv_exit_status()
                return exit_status == 0

            success = await loop.run_in_executor(None, _run)
            return success
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return False
