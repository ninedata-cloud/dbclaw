"""测试网络连接表格数据"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_session_factory
from backend.models.host import Host
from backend.services.ssh_connection_pool import get_ssh_pool
from backend.services.host_process_service import HostProcessService
from sqlalchemy import select


async def test_network_connections():
    """测试网络连接数据采集"""
    print("=" * 60)
    print("测试网络连接表格数据")
    print("=" * 60)

    session_factory = get_session_factory()
    async with session_factory() as db:
        # 获取第一个主机
        result = await db.execute(select(Host).where(Host.deleted_at.is_(None)).limit(1))
        host = result.scalar_one_or_none()

        if not host:
            print("❌ 没有找到主机")
            return False

        print(f"\n✓ 找到主机: {host.name} ({host.host}:{host.port})")

        ssh_pool = get_ssh_pool()

        try:
            async with ssh_pool.get_connection(db, host.id) as ssh_client:
                print("\n✓ SSH 连接成功")

                # 找一个有网络连接的进程
                stdin, stdout, stderr = ssh_client.exec_command(
                    "ps aux | grep -E 'sshd|python|java|nginx' | grep -v grep | head -5",
                    timeout=5
                )
                ps_list = stdout.read().decode('utf-8', errors='replace')
                lines = ps_list.strip().split('\n')

                if len(lines) < 1:
                    print("❌ 无法找到有网络连接的进程")
                    return False

                # 尝试多个进程，找到有网络连接的
                for line in lines:
                    parts = line.split(None, 10)
                    if len(parts) < 2:
                        continue

                    test_pid = int(parts[1])
                    print(f"\n测试 PID: {test_pid} ({parts[10][:50]}...)")

                    # 获取进程详情
                    detail = await HostProcessService.get_process_detail(ssh_client, test_pid)

                    if detail['network_connections']:
                        print(f"\n✓ 找到 {len(detail['network_connections'])} 个网络连接")
                        print("\n" + "=" * 60)
                        print("网络连接详情")
                        print("=" * 60)

                        # 打印表格
                        print(f"\n{'状态':<12} {'本地地址':<20} {'端口':<8} {'远程地址':<20} {'端口':<8} {'接收':<10} {'发送':<10}")
                        print("-" * 100)

                        for i, conn in enumerate(detail['network_connections'][:10], 1):
                            print(f"{conn['state']:<12} "
                                  f"{conn['local_address']:<20} "
                                  f"{conn['local_port']:<8} "
                                  f"{conn['remote_address']:<20} "
                                  f"{conn['remote_port']:<8} "
                                  f"{conn['recv_bytes']:<10} "
                                  f"{conn['send_bytes']:<10}")

                        if len(detail['network_connections']) > 10:
                            print(f"\n... 还有 {len(detail['network_connections']) - 10} 个连接")

                        print("\n" + "=" * 60)
                        print("✓ 测试通过")
                        print("=" * 60)
                        return True

                print("\n⚠ 未找到有网络连接的进程")
                return False

        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == '__main__':
    success = asyncio.run(test_network_connections())
    sys.exit(0 if success else 1)
