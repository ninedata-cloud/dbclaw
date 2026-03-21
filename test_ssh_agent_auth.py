"""
测试 SSH Agent 认证功能

运行方式：
    python test_ssh_agent_auth.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.ssh_service import SSHService


async def test_ssh_agent():
    """测试 SSH Agent 认证"""
    print("=== SSH Agent 认证测试 ===\n")

    # 配置测试参数（请根据实际环境修改）
    test_host = "localhost"  # 或实际的远程主机
    test_port = 22
    test_username = "william"  # 当前用户

    print(f"测试配置：")
    print(f"  主机: {test_host}")
    print(f"  端口: {test_port}")
    print(f"  用户: {test_username}")
    print(f"  认证: SSH Agent\n")

    try:
        # 创建 SSH 服务实例（使用 Agent 认证）
        ssh = SSHService(
            host=test_host,
            port=test_port,
            username=test_username,
            use_agent=True
        )

        print("1. 测试基本连接...")
        output = ssh.execute("echo 'SSH Agent 认证成功'")
        print(f"   ✓ 输出: {output.strip()}\n")

        print("2. 测试系统信息获取...")
        output = ssh.execute("uname -a")
        print(f"   ✓ 系统: {output.strip()}\n")

        print("3. 测试当前用户...")
        output = ssh.execute("whoami")
        print(f"   ✓ 用户: {output.strip()}\n")

        print("4. 测试主机名...")
        output = ssh.execute("hostname")
        print(f"   ✓ 主机名: {output.strip()}\n")

        print("✓ 所有测试通过！SSH Agent 认证工作正常。\n")

    except Exception as e:
        print(f"✗ 测试失败: {e}\n")
        print("故障排查建议：")
        print("1. 检查 SSH Agent 是否运行：ssh-add -l")
        print("2. 确保已添加密钥：ssh-add ~/.ssh/id_rsa")
        print("3. 验证能否直接 SSH 连接：ssh {}@{}".format(test_username, test_host))
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(test_ssh_agent())
    sys.exit(0 if success else 1)
