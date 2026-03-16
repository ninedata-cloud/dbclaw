"""Host metrics collector - collects CPU, memory, disk usage from SSH hosts"""
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import async_session
from backend.models.host import Host
from backend.models.host_metric import HostMetric
from backend.services.ssh_service import SSHService
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


async def collect_host_metrics():
    """Collect metrics from all SSH hosts every minute"""
    while True:
        try:
            async with async_session() as db:
                result = await db.execute(select(Host))
                hosts = result.scalars().all()

                for host in hosts:
                    try:
                        await _collect_host_metrics(db, host)
                    except Exception as e:
                        logger.error(f"Failed to collect metrics for host {host.name}: {e}")

                await db.commit()
        except Exception as e:
            logger.error(f"SSH host metrics collection error: {e}")

        await asyncio.sleep(60)


async def _collect_host_metrics(db: AsyncSession, host: Host):
    """Collect metrics for a single SSH host"""
    try:
        password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
        private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None

        ssh = SSHService(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password,
            private_key=private_key
        )

        # Execute commands to get metrics (SSHService.execute_multi is blocking, run in executor)
        loop = asyncio.get_event_loop()
        commands = [
            "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1",
            "free | grep Mem | awk '{print ($3/$2) * 100.0}'",
            "df -h / | tail -1 | awk '{print $5}' | cut -d'%' -f1"
        ]

        results = await loop.run_in_executor(None, ssh.execute_multi, commands)

        # Parse results
        values = list(results.values())
        cpu_usage = float(values[0].strip() or 0)
        memory_usage = float(values[1].strip() or 0)
        disk_usage = float(values[2].strip() or 0)

        # Save to host_metrics table
        metric = HostMetric(
            host_id=host.id,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage
        )
        db.add(metric)

    except Exception as e:
        logger.error(f"Failed to collect metrics for {host.name}: {e}")
