"""
SSH command execution utility
"""
import asyncio
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.host import Host
from backend.services.ssh_connection_pool import get_ssh_pool
from backend.utils.command_safety import DANGEROUS_COMMAND_PATTERNS, first_matching_command_pattern


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
            pattern = first_matching_command_pattern(command, DANGEROUS_COMMAND_PATTERNS)
            if pattern:
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

        # Execute command through SSH connection pool
        ssh_pool = get_ssh_pool()
        exec_timeout = timeout if timeout is not None else 30

        async with ssh_pool.get_connection(db, host_id) as ssh_client:
            loop = asyncio.get_event_loop()

            def _run():
                stdin, stdout, stderr = ssh_client.exec_command(command, timeout=exec_timeout)
                output = stdout.read().decode("utf-8", errors="replace")
                err = stderr.read().decode("utf-8", errors="replace")
                if err and not output:
                    return err
                return output

            output = await loop.run_in_executor(None, _run)

        return {
            "success": True,
            "output": output,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
