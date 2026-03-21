"""Host metrics collector - collects CPU, memory, disk usage from SSH hosts"""
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import async_session
from backend.models.host import Host
from backend.models.host_metric import HostMetric

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
    """Collect metrics for a single SSH host using connection pool + OSMetricsCollector"""
    try:
        from backend.services.ssh_connection_pool import get_ssh_pool
        from backend.services.os_metrics_collector import OSMetricsCollector

        ssh_pool = get_ssh_pool()

        try:
            async with ssh_pool.get_connection(db, host.id) as ssh_client:
                # 使用 OSMetricsCollector 采集完整指标
                os_metrics = await asyncio.wait_for(
                    OSMetricsCollector.collect_via_ssh(ssh_client, os_type='linux'),
                    timeout=30.0
                )

                # 提取核心指标，带安全的类型转换
                cpu_usage = _safe_float(os_metrics.get('cpu_usage'))
                memory_usage = _safe_float(os_metrics.get('memory_usage'))
                disk_usage = _safe_float(os_metrics.get('disk_usage'))

                # Save to host_metrics table
                metric = HostMetric(
                    host_id=host.id,
                    cpu_usage=cpu_usage,
                    memory_usage=memory_usage,
                    disk_usage=disk_usage,
                    data=os_metrics if os_metrics else None,
                )
                db.add(metric)

        except asyncio.TimeoutError:
            logger.warning(f"SSH metrics collection timeout for host {host.name} (id={host.id})")
        except ConnectionError as e:
            logger.warning(f"Failed to get SSH connection for host {host.name}: {e}")
        except Exception as e:
            logger.error(f"Failed to collect metrics for {host.name}: {e}")

    except Exception as e:
        logger.error(f"Error in _collect_host_metrics: {e}")


def _safe_float(value) -> float:
    """安全地将值转换为 float，失败返回 None"""
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (ValueError, TypeError):
        return None
