"""调试进程详情数据采集"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_session_factory
from backend.models.host import Host
from backend.services.ssh_connection_pool import get_ssh_pool
from sqlalchemy import select


async def debug_process_detail():
    """调试进程详情采集"""
    print("=" * 60)
    print("调试进程详情数据采集")
    print("=" * 60)

    session_factory = get_session_factory()
    async with session_factory() as db:
        # 获取第一个主机
        result = await db.execute(select(Host).where(Host.deleted_at.is_(None)).limit(1))
        host = result.scalar_one_or_none()

        if not host:
            print("❌ 没有找到主机")
            return

        print(f"\n✓ 找到主机: {host.name} ({host.host}:{host.port})")

        ssh_pool = get_ssh_pool()

        try:
            async with ssh_pool.get_connection(db, host.id) as ssh_client:
                print("\n✓ SSH 连接成功")

                # 先获取进程列表，找一个真实的PID
                print("\n1. 获取进程列表...")
                stdin, stdout, stderr = ssh_client.exec_command("ps aux | head -10", timeout=5)
                ps_list = stdout.read().decode('utf-8', errors='replace')
                print(ps_list)

                # 提取第一个进程的PID
                lines = ps_list.strip().split('\n')
                if len(lines) < 2:
                    print("❌ 无法获取进程列表")
                    return

                parts = lines[1].split(None, 10)
                test_pid = int(parts[1])
                print(f"\n✓ 使用测试PID: {test_pid}")

                # 测试各个命令
                print("\n2. 测试 /proc/{pid}/io 命令...")
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"cat /proc/{test_pid}/io 2>&1",
                    timeout=5
                )
                io_output = stdout.read().decode('utf-8', errors='replace')
                print(f"输出:\n{io_output}")

                # 测试权限
                print("\n3. 测试权限...")
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"ls -la /proc/{test_pid}/io 2>&1",
                    timeout=5
                )
                ls_output = stdout.read().decode('utf-8', errors='replace')
                print(f"文件权限:\n{ls_output}")

                # 测试 sudo
                print("\n4. 测试 sudo 权限...")
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"sudo -n cat /proc/{test_pid}/io 2>&1",
                    timeout=5
                )
                sudo_output = stdout.read().decode('utf-8', errors='replace')
                print(f"Sudo 输出:\n{sudo_output}")

                # 测试网络连接
                print("\n5. 测试网络连接命令...")
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"lsof -p {test_pid} -i -n -P 2>&1",
                    timeout=5
                )
                lsof_output = stdout.read().decode('utf-8', errors='replace')
                print(f"lsof 输出:\n{lsof_output}")

                # 测试 netstat
                print("\n6. 测试 netstat 命令...")
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"netstat -tnp 2>&1 | grep {test_pid}",
                    timeout=5
                )
                netstat_output = stdout.read().decode('utf-8', errors='replace')
                print(f"netstat 输出:\n{netstat_output}")

                # 测试 ss 命令
                print("\n7. 测试 ss 命令...")
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"ss -tnp 2>&1 | grep pid={test_pid}",
                    timeout=5
                )
                ss_output = stdout.read().decode('utf-8', errors='replace')
                print(f"ss 输出:\n{ss_output}")

        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(debug_process_detail())
