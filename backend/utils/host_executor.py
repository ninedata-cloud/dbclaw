"""
SSH command execution utility
"""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.host import Host
from backend.services.ssh_service import SSHService
from backend.utils.encryption import decrypt_value


async def execute_host_command(db: AsyncSession, host_id: int, command: str, allow_write: bool = False, timeout: int = None) -> Dict[str, Any]:
    """Execute a command on an SSH host

    Args:
        db: Database session
        host_id: SSH host ID
        command: Shell command to execute
        allow_write: If False (default), only read-only commands are allowed.
                     If True, all commands including destructive operations are allowed.
        timeout: Command execution timeout in seconds (default: 30s)
    """
    try:
        # Validate command if write operations are not allowed
        if not allow_write:
            # List of dangerous command patterns
            dangerous_patterns = [
                'rm ', 'rmdir', 'del ', 'delete',
                'mv ', 'move',
                'chmod', 'chown', 'chgrp',
                'kill', 'pkill', 'killall',
                'shutdown', 'reboot', 'halt', 'poweroff',
                'mkfs', 'fdisk', 'parted',
                'dd ', 'format',
                'iptables', 'firewall',
                'useradd', 'userdel', 'usermod',
                'groupadd', 'groupdel',
                '>>', 'tee',
                'wget', 'curl -o', 'curl -O',
                'apt install', 'yum install', 'dnf install',
                'systemctl stop', 'systemctl start', 'systemctl restart',
                'service stop', 'service start', 'service restart',
            ]

            command_lower = command.lower()
            for pattern in dangerous_patterns:
                if pattern in command_lower:
                    return {
                        "success": False,
                        "error": f"Command contains potentially dangerous operation '{pattern}'. Enable 'Execute Any OS Command' permission for write operations."
                    }

        # Get host
        result = await db.execute(
            select(Host).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()

        if not host:
            return {"success": False, "error": f"Host {host_id} not found"}

        # Decrypt credentials based on auth type
        password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
        private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
        use_agent = (host.auth_type == 'agent')

        # Create SSH service with proper auth
        ssh_service = SSHService(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password,
            private_key=private_key,
            use_agent=use_agent,
        )

        # Execute command (SSHService.execute is synchronous, run in executor)
        import asyncio
        loop = asyncio.get_event_loop()

        # Use provided timeout or default to 30s
        exec_timeout = timeout if timeout is not None else 30
        output = await loop.run_in_executor(None, ssh_service.execute, command, exec_timeout)

        return {
            "success": True,
            "output": output,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
