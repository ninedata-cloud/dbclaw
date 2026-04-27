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
    async def get_process_detail(ssh_client, pid: int) -> Dict[str, Any]:
        """获取进程详细信息，包括命令详情、网络IO和磁盘IO"""
        try:
            loop = asyncio.get_event_loop()

            def _run():
                # 获取进程基本信息
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"ps -p {pid} -o user,pid,%cpu,%mem,vsz,rss,stat,start,time,command",
                    timeout=5
                )
                ps_output = stdout.read().decode('utf-8', errors='replace')

                # 获取完整命令行
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"cat /proc/{pid}/cmdline 2>/dev/null | tr '\\0' ' '",
                    timeout=5
                )
                cmdline = stdout.read().decode('utf-8', errors='replace').strip()

                # 获取进程IO统计 - 尝试 sudo，如果失败则尝试普通读取
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"sudo -n cat /proc/{pid}/io 2>/dev/null || cat /proc/{pid}/io 2>/dev/null",
                    timeout=5
                )
                io_output = stdout.read().decode('utf-8', errors='replace')

                # 获取进程网络连接 - 使用 ss 命令获取详细信息
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"sudo -n ss -tnp state established 2>/dev/null | grep 'pid={pid}' || "
                    f"ss -tnp state established 2>/dev/null | grep 'pid={pid}'",
                    timeout=5
                )
                network_output = stdout.read().decode('utf-8', errors='replace')

                # 获取网络流量统计 - 从 /proc/net/dev 读取
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"cat /proc/{pid}/net/dev 2>/dev/null || cat /proc/net/dev 2>/dev/null",
                    timeout=5
                )
                net_dev_output = stdout.read().decode('utf-8', errors='replace')

                # 获取进程的文件描述符，找出网络套接字
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"ls -l /proc/{pid}/fd 2>/dev/null | grep socket",
                    timeout=5
                )
                fd_output = stdout.read().decode('utf-8', errors='replace')

                # 获取进程环境变量
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"cat /proc/{pid}/environ 2>/dev/null | tr '\\0' '\\n'",
                    timeout=5
                )
                environ_output = stdout.read().decode('utf-8', errors='replace')

                # 获取进程工作目录
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"readlink /proc/{pid}/cwd 2>/dev/null",
                    timeout=5
                )
                cwd = stdout.read().decode('utf-8', errors='replace').strip()

                return {
                    'ps_output': ps_output,
                    'cmdline': cmdline,
                    'io_output': io_output,
                    'network_output': network_output,
                    'net_dev_output': net_dev_output,
                    'fd_output': fd_output,
                    'environ_output': environ_output,
                    'cwd': cwd
                }

            result = await loop.run_in_executor(None, _run)
            return HostProcessService._parse_process_detail(pid, result)
        except Exception as e:
            logger.error(f"Failed to get process detail for {pid}: {e}")
            raise

    @staticmethod
    def _parse_process_detail(pid: int, raw_data: Dict[str, str]) -> Dict[str, Any]:
        """解析进程详细信息"""
        detail = {
            'pid': pid,
            'user': None,
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'vsz': 0,
            'rss': 0,
            'state': None,
            'start_time': None,
            'cpu_time': None,
            'command': None,
            'cmdline': raw_data['cmdline'] or None,
            'cwd': raw_data['cwd'] or None,
            'io': {},
            'network_connections': [],
            'environment': {}
        }

        # 解析 ps 输出
        ps_lines = raw_data['ps_output'].strip().split('\n')
        if len(ps_lines) >= 2:
            try:
                parts = ps_lines[1].split(None, 9)
                if len(parts) >= 10:
                    detail['user'] = parts[0]
                    detail['cpu_percent'] = float(parts[2])
                    detail['memory_percent'] = float(parts[3])
                    detail['vsz'] = int(parts[4])
                    detail['rss'] = int(parts[5])
                    detail['state'] = parts[6]
                    detail['start_time'] = parts[7]
                    detail['cpu_time'] = parts[8]
                    detail['command'] = parts[9]
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse ps output: {e}")

        # 解析 IO 统计
        io_data = {}
        for line in raw_data['io_output'].strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                try:
                    io_data[key.strip()] = int(value.strip())
                except ValueError:
                    pass

        detail['io'] = {
            'read_bytes': io_data.get('read_bytes', 0),
            'write_bytes': io_data.get('write_bytes', 0),
            'read_chars': io_data.get('rchar', 0),
            'write_chars': io_data.get('wchar', 0),
            'read_syscalls': io_data.get('syscr', 0),
            'write_syscalls': io_data.get('syscw', 0)
        }

        # 解析网络连接 - ss 命令输出
        connections = []
        for line in raw_data['network_output'].strip().split('\n'):
            if not line or 'Recv-Q' in line or 'Local Address' in line:
                continue

            try:
                # ss 输出格式: Recv-Q Send-Q Local Address:Port Peer Address:Port [Process]
                # 示例: 0 0 192.168.2.29:37892 192.168.2.3:9022 user:(("python",pid=12927,fd=182))
                parts = line.split()
                if len(parts) >= 4:
                    recv_q = int(parts[0]) if parts[0].isdigit() else 0
                    send_q = int(parts[1]) if parts[1].isdigit() else 0
                    local_addr = parts[2]
                    peer_addr = parts[3]

                    # 解析本地和远程地址
                    if ':' in local_addr:
                        local_parts = local_addr.rsplit(':', 1)
                        local_ip = local_parts[0]
                        local_port = local_parts[1]
                    else:
                        local_ip = local_addr
                        local_port = ''

                    if ':' in peer_addr:
                        peer_parts = peer_addr.rsplit(':', 1)
                        peer_ip = peer_parts[0]
                        peer_port = peer_parts[1]
                    else:
                        peer_ip = peer_addr
                        peer_port = ''

                    connections.append({
                        'state': 'ESTABLISHED',  # ss state established 只返回已建立的连接
                        'local_address': local_ip,
                        'local_port': local_port,
                        'remote_address': peer_ip,
                        'remote_port': peer_port,
                        'recv_bytes': recv_q,
                        'send_bytes': send_q
                    })
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse network connection line: {line[:50]}... Error: {e}")
                continue

        detail['network_connections'] = connections

        # 解析环境变量（只保留前20个，避免过大）
        env_lines = raw_data['environ_output'].strip().split('\n')
        for i, line in enumerate(env_lines[:20]):
            if '=' in line:
                key, value = line.split('=', 1)
                detail['environment'][key] = value

        return detail

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
