"""测试修复后的进程详情功能"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_session_factory
from backend.models.host import Host
from backend.services.ssh_connection_pool import get_ssh_pool
from backend.services.host_process_service import HostProcessService
from sqlalchemy import select


async def test_fixed_process_detail():
    """测试修复后的进程详情采集"""
    print("=" * 60)
    print("测试修复后的进程详情功能")
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

                # 获取一个真实的进程PID
                stdin, stdout, stderr = ssh_client.exec_command("ps aux | head -5", timeout=5)
                ps_list = stdout.read().decode('utf-8', errors='replace')
                lines = ps_list.strip().split('\n')

                if len(lines) < 2:
                    print("❌ 无法获取进程列表")
                    return False

                parts = lines[1].split(None, 10)
                test_pid = int(parts[1])
                print(f"\n测试 PID: {test_pid}")

                # 调用修复后的函数
                print("\n正在获取进程详情...")
                detail = await HostProcessService.get_process_detail(ssh_client, test_pid)

                print("\n" + "=" * 60)
                print("进程详情结果")
                print("=" * 60)

                print(f"\n【基本信息】")
                print(f"  PID: {detail['pid']}")
                print(f"  用户: {detail['user']}")
                print(f"  CPU: {detail['cpu_percent']}%")
                print(f"  内存: {detail['memory_percent']}%")
                print(f"  状态: {detail['state']}")
                print(f"  启动时间: {detail['start_time']}")
                print(f"  CPU 时间: {detail['cpu_time']}")
                print(f"  工作目录: {detail['cwd']}")

                print(f"\n【命令】")
                print(f"  命令: {detail['command'][:100]}...")
                if detail['cmdline']:
                    print(f"  完整命令行: {detail['cmdline'][:100]}...")

                print(f"\n【磁盘 I/O】")
                io = detail['io']
                print(f"  读取字节: {io['read_bytes']:,} bytes")
                print(f"  写入字节: {io['write_bytes']:,} bytes")
                print(f"  读取字符: {io['read_chars']:,} bytes")
                print(f"  写入字符: {io['write_chars']:,} bytes")
                print(f"  读取系统调用: {io['read_syscalls']:,}")
                print(f"  写入系统调用: {io['write_syscalls']:,}")

                print(f"\n【网络连接】")
                if detail['network_connections']:
                    print(f"  连接数: {len(detail['network_connections'])}")
                    for i, conn in enumerate(detail['network_connections'][:5], 1):
                        print(f"  {i}. {conn[:80]}")
                    if len(detail['network_connections']) > 5:
                        print(f"  ... 还有 {len(detail['network_connections']) - 5} 个连接")
                else:
                    print("  无网络连接")

                print(f"\n【环境变量】")
                if detail['environment']:
                    print(f"  变量数: {len(detail['environment'])}")
                    for i, (key, value) in enumerate(list(detail['environment'].items())[:5], 1):
                        print(f"  {i}. {key}={value[:50]}")
                    if len(detail['environment']) > 5:
                        print(f"  ... 还有 {len(detail['environment']) - 5} 个变量")
                else:
                    print("  无环境变量")

                # 验证关键数据
                print("\n" + "=" * 60)
                print("数据验证")
                print("=" * 60)

                success = True

                if detail['pid'] != test_pid:
                    print("❌ PID 不匹配")
                    success = False
                else:
                    print("✓ PID 正确")

                if not detail['user']:
                    print("❌ 用户信息缺失")
                    success = False
                else:
                    print(f"✓ 用户信息: {detail['user']}")

                if io['read_bytes'] > 0 or io['write_bytes'] > 0:
                    print(f"✓ 磁盘 I/O 数据已采集 (读: {io['read_bytes']:,}, 写: {io['write_bytes']:,})")
                else:
                    print("⚠ 磁盘 I/O 数据为 0 (可能需要 sudo 权限)")

                if detail['network_connections']:
                    print(f"✓ 网络连接已采集 ({len(detail['network_connections'])} 个)")
                else:
                    print("⚠ 无网络连接数据")

                print("\n" + "=" * 60)
                if success:
                    print("✓ 测试通过")
                else:
                    print("⚠ 测试部分通过")
                print("=" * 60)

                return success

        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == '__main__':
    success = asyncio.run(test_fixed_process_detail())
    sys.exit(0 if success else 1)
