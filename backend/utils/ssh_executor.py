"""
SSH command execution utility
"""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.ssh_host import SSHHost
from backend.services.ssh_service import SSHService
from backend.utils.encryption import decrypt_value


async def execute_ssh_command(db: AsyncSession, ssh_host_id: int, command: str, allow_write: bool = False) -> Dict[str, Any]:
    """Execute a command on an SSH host

    Args:
        db: Database session
        ssh_host_id: SSH host ID
        command: Shell command to execute
        allow_write: If False (default), only read-only commands are allowed.
                     If True, all commands including destructive operations are allowed.
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
                '>', '>>', '|', 'tee',
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

        # Get SSH host
        result = await db.execute(
            select(SSHHost).where(SSHHost.id == ssh_host_id)
        )
        ssh_host = result.scalar_one_or_none()

        if not ssh_host:
            return {"success": False, "error": f"SSH host {ssh_host_id} not found"}

        # Decrypt password
        password = decrypt_value(ssh_host.password_encrypted) if ssh_host.password_encrypted else None

        # Create SSH service
        ssh_service = SSHService(
            host=ssh_host.host,
            port=ssh_host.port,
            username=ssh_host.username,
            password=password,
        )

        # Execute command (SSHService.execute is synchronous, run in executor)
        import asyncio
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, ssh_service.execute, command)

        return {
            "success": True,
            "output": output,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
