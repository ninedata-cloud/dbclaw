"""
批量更新主机 OS 版本信息

遍历所有主机，通过 SSH 连接采集 OS 版本信息并更新到数据库。

运行方式：
source .venv/bin/activate && PYTHONPATH=. python backend/migrations/batch_update_host_os_version.py
"""

import asyncio
import logging
from backend.database import async_session
from backend.models.host import Host
from backend.models.soft_delete import alive_select
from backend.utils.encryption import decrypt_value

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def _get_os_version_via_ssh(host: str, port: int, username: str, password: str = None, private_key: str = None, use_agent: bool = False) -> str | None:
    """通过 SSH 获取操作系统版本"""
    try:
        from backend.services.ssh_service import SSHService
        ssh = SSHService(
            host=host,
            port=port,
            username=username,
            password=password,
            private_key=private_key,
            use_agent=use_agent,
        )
        # 尝试获取 OS 版本信息
        output = ssh.execute("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME || uname -a")
        if output:
            # 解析 PRETTY_NAME=xxx 格式
            for line in output.strip().split('\n'):
                if 'PRETTY_NAME' in line:
                    return line.split('=')[1].strip().strip('"')
            return output.strip()[:255]  # fallback to uname output
    except Exception as e:
        logger.warning(f"Failed to get OS version for {host}: {e}")
    return None


async def batch_update_os_versions():
    """批量更新所有主机的 OS 版本"""
    async with async_session() as db:
        result = await db.execute(alive_select(Host))
        host = result.scalars().all()

        if not host:
            logger.info("No host found")
            return

        logger.info(f"Found {len(host)} host, starting OS version collection...")

        success_count = 0
        fail_count = 0

        for host in host:
            # 获取密码/私钥
            password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
            private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
            use_agent = (host.auth_type == "agent")

            # SSH 获取 OS 版本
            os_version = await _get_os_version_via_ssh(
                host=host.host,
                port=host.port,
                username=host.username,
                password=password,
                private_key=private_key,
                use_agent=use_agent,
            )

            if os_version:
                host.os_version = os_version
                logger.info(f"[{host.id}] {host.name}: {os_version}")
                success_count += 1
            else:
                logger.warning(f"[{host.id}] {host.name}: Failed to get OS version")
                fail_count += 1

        await db.commit()

        logger.info(f"Batch update complete: {success_count} success, {fail_count} failed")


if __name__ == "__main__":
    asyncio.run(batch_update_os_versions())
