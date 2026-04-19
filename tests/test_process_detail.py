"""测试进程详情功能"""
import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.host_process_service import HostProcessService


class MockSSHClient:
    """模拟 SSH 客户端"""

    def __init__(self, pid=1234):
        self.pid = pid

    def exec_command(self, command, timeout=None):
        """模拟执行命令"""
        class MockChannel:
            def recv_exit_status(self):
                return 0

        class MockStdout:
            def __init__(self, data):
                self.data = data
                self.channel = MockChannel()

            def read(self):
                return self.data.encode('utf-8')

        # 根据命令返回不同的模拟数据
        if f'ps -p {self.pid}' in command:
            data = f"""USER       PID %CPU %MEM    VSZ   RSS STAT START   TIME COMMAND
root      {self.pid}  2.5  1.3 123456 67890 Ss   10:30 0:05:23 /usr/bin/python3 /app/main.py"""

        elif f'cat /proc/{self.pid}/cmdline' in command:
            data = '/usr/bin/python3 /app/main.py --config /etc/app.conf'

        elif f'cat /proc/{self.pid}/io' in command:
            data = """rchar: 1234567890
wchar: 987654321
syscr: 12345
syscw: 6789
read_bytes: 102400000
write_bytes: 51200000
cancelled_write_bytes: 0"""

        elif f'lsof -p {self.pid}' in command or f'netstat -tnp' in command:
            data = f"""python3  {self.pid} root    3u  IPv4  12345      0t0  TCP 127.0.0.1:8000 (LISTEN)
python3  {self.pid} root    4u  IPv4  12346      0t0  TCP 127.0.0.1:8000->192.168.1.100:54321 (ESTABLISHED)"""

        elif f'cat /proc/{self.pid}/environ' in command:
            data = """PATH=/usr/local/bin:/usr/bin:/bin
HOME=/root
USER=root
LANG=en_US.UTF-8
PYTHONPATH=/app"""

        elif f'readlink /proc/{self.pid}/cwd' in command:
            data = '/app'

        else:
            data = ''

        return None, MockStdout(data), None


async def test_get_process_detail():
    """测试获取进程详情"""
    print("测试获取进程详情...")

    mock_ssh = MockSSHClient(pid=1234)

    try:
        detail = await HostProcessService.get_process_detail(mock_ssh, 1234)

        print("\n✓ 成功获取进程详情")
        print(f"  PID: {detail['pid']}")
        print(f"  用户: {detail['user']}")
        print(f"  CPU: {detail['cpu_percent']}%")
        print(f"  内存: {detail['memory_percent']}%")
        print(f"  状态: {detail['state']}")
        print(f"  命令: {detail['command']}")
        print(f"  完整命令行: {detail['cmdline']}")
        print(f"  工作目录: {detail['cwd']}")
        print(f"  读取字节: {detail['io']['read_bytes']:,}")
        print(f"  写入字节: {detail['io']['write_bytes']:,}")
        print(f"  网络连接数: {len(detail['network_connections'])}")
        print(f"  环境变量数: {len(detail['environment'])}")

        # 验证关键字段
        assert detail['pid'] == 1234
        assert detail['user'] == 'root'
        assert detail['cpu_percent'] == 2.5
        assert detail['memory_percent'] == 1.3
        assert detail['state'] == 'Ss'
        assert detail['io']['read_bytes'] == 102400000
        assert detail['io']['write_bytes'] == 51200000
        assert len(detail['network_connections']) == 2
        assert 'PATH' in detail['environment']

        print("\n✓ 所有断言通过")
        return True

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("进程详情功能测试")
    print("=" * 60)

    success = await test_get_process_detail()

    print("\n" + "=" * 60)
    if success:
        print("✓ 所有测试通过")
        print("=" * 60)
        return 0
    else:
        print("✗ 测试失败")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
