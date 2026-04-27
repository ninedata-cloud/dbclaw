import asyncio
import logging
import re
from typing import List, Dict, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class HostNetworkService:
    """主机网络连接采集服务"""

    @staticmethod
    async def get_connections(ssh_client) -> List[Dict[str, Any]]:
        """通过 SSH 获取网络连接列表"""
        try:
            loop = asyncio.get_event_loop()

            def _run():
                # 优先使用 ss，回退到 netstat
                stdin, stdout, stderr = ssh_client.exec_command(
                    "ss -tunap 2>/dev/null || netstat -tunap 2>/dev/null",
                    timeout=10
                )
                return stdout.read().decode('utf-8', errors='replace')

            output = await loop.run_in_executor(None, _run)
            return HostNetworkService._parse_ss_output(output)
        except Exception as e:
            logger.error(f"Failed to get connections: {e}")
            return []

    @staticmethod
    def _parse_ss_output(output: str) -> List[Dict[str, Any]]:
        """解析 ss/netstat 输出"""
        connections = []
        lines = output.strip().split('\n')

        for line in lines:
            try:
                # 跳过表头和空行
                if not line or line.startswith('Netid') or line.startswith('Proto') or line.startswith('Active'):
                    continue

                # ss 格式: tcp ESTAB 0 0 192.168.1.10:22 192.168.1.100:54321 user:(("sshd",pid=1234,fd=3))
                # netstat 格式: tcp 0 0 192.168.1.10:22 192.168.1.100:54321 ESTABLISHED 1234/sshd

                parts = line.split()
                if len(parts) < 5:
                    continue

                proto = parts[0].lower()
                if proto not in ['tcp', 'udp']:
                    continue

                # 解析本地地址和远程地址
                local_addr = parts[3] if 'ss' in output[:100].lower() else parts[3]
                remote_addr = parts[4] if 'ss' in output[:100].lower() else parts[4]

                local_ip, local_port = HostNetworkService._parse_address(local_addr)
                remote_ip, remote_port = HostNetworkService._parse_address(remote_addr)

                if not local_ip or not remote_ip:
                    continue

                # 解析状态
                state = parts[1] if 'ss' in output[:100].lower() else (parts[5] if len(parts) > 5 else 'UNKNOWN')

                # 解析进程信息
                process_name = None
                pid = None
                if len(parts) > 6:
                    # ss 格式: user:(("sshd",pid=1234,fd=3))
                    process_match = re.search(r'\("([^"]+)",pid=(\d+)', line)
                    if process_match:
                        process_name = process_match.group(1)
                        pid = int(process_match.group(2))
                    else:
                        # netstat 格式: 1234/sshd
                        process_match = re.search(r'(\d+)/(\S+)', parts[-1])
                        if process_match:
                            pid = int(process_match.group(1))
                            process_name = process_match.group(2)

                connections.append({
                    'local_ip': local_ip,
                    'local_port': local_port,
                    'remote_ip': remote_ip,
                    'remote_port': remote_port,
                    'state': state,
                    'process_name': process_name,
                    'pid': pid
                })
            except Exception as e:
                logger.debug(f"Failed to parse connection line: {line[:50]}... Error: {e}")
                continue

        return connections

    @staticmethod
    def _parse_address(addr: str) -> tuple:
        """解析地址字符串，返回 (ip, port)"""
        try:
            # 处理 IPv6 格式 [::1]:22
            if addr.startswith('['):
                match = re.match(r'\[([^\]]+)\]:(\d+)', addr)
                if match:
                    return match.group(1), int(match.group(2))

            # 处理 IPv4 格式 192.168.1.10:22
            if ':' in addr:
                parts = addr.rsplit(':', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    return parts[0], int(parts[1])

            return None, None
        except Exception:
            return None, None

    @staticmethod
    def aggregate_connections(connections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按远程 IP 聚合连接"""
        topology = defaultdict(lambda: {
            'remote_ip': '',
            'connection_count': 0,
            'ports': set(),
            'states': defaultdict(int),
            'processes': set()
        })

        for conn in connections:
            remote_ip = conn['remote_ip']

            # 跳过本地回环地址
            if remote_ip in ['127.0.0.1', '::1', 'localhost']:
                continue

            topology[remote_ip]['remote_ip'] = remote_ip
            topology[remote_ip]['connection_count'] += 1
            topology[remote_ip]['ports'].add(conn['remote_port'])
            topology[remote_ip]['states'][conn['state']] += 1

            if conn['process_name']:
                topology[remote_ip]['processes'].add(conn['process_name'])

        # 转换为列表格式
        result = []
        for data in topology.values():
            result.append({
                'remote_ip': data['remote_ip'],
                'connection_count': data['connection_count'],
                'ports': sorted(list(data['ports']))[:10],  # 最多显示 10 个端口
                'states': dict(data['states']),
                'processes': list(data['processes'])[:5]  # 最多显示 5 个进程
            })

        # 按连接数排序
        result.sort(key=lambda x: x['connection_count'], reverse=True)
        return result[:50]  # 最多返回 50 个远程 IP
