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
        from sqlalchemy import select, desc
        from backend.models.host_metric import HostMetric

        ssh_pool = get_ssh_pool()

        try:
            async with ssh_pool.get_connection(db, host.id) as ssh_client:
                # 使用 OSMetricsCollector 采集完整指标
                os_metrics = await asyncio.wait_for(
                    OSMetricsCollector.collect_via_ssh(ssh_client, os_type='linux'),
                    timeout=30.0
                )

                # 获取上一次采集的指标，用于计算速率
                result = await db.execute(
                    select(HostMetric)
                    .where(HostMetric.host_id == host.id)
                    .order_by(desc(HostMetric.collected_at))
                    .limit(1)
                )
                last_metric = result.scalar_one_or_none()

                # 计算磁盘 IO 速率
                if last_metric and last_metric.data:
                    _calculate_disk_io_rates(os_metrics, last_metric.data, last_metric.collected_at)

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


def _calculate_disk_io_rates(current_metrics: dict, last_data: dict, last_collected_at):
    """
    根据上一次采集的累计值计算磁盘 IO 速率

    Args:
        current_metrics: 当前采集的指标字典（会被修改，添加速率字段）
        last_data: 上一次采集的 data 字段
        last_collected_at: 上一次采集时间
    """
    from datetime import datetime, timezone

    # 提取当前累计值
    curr_reads = current_metrics.get('disk_reads_total')
    curr_writes = current_metrics.get('disk_writes_total')
    curr_read_sectors = current_metrics.get('disk_read_sectors_total')
    curr_write_sectors = current_metrics.get('disk_write_sectors_total')

    # 提取上一次累计值
    last_reads = last_data.get('disk_reads_total')
    last_writes = last_data.get('disk_writes_total')
    last_read_sectors = last_data.get('disk_read_sectors_total')
    last_write_sectors = last_data.get('disk_write_sectors_total')

    # 如果任一值缺失，无法计算速率
    if None in [curr_reads, curr_writes, curr_read_sectors, curr_write_sectors,
                last_reads, last_writes, last_read_sectors, last_write_sectors]:
        return

    # 计算时间差（秒）
    now = datetime.now(timezone.utc)
    if last_collected_at.tzinfo is None:
        # 如果数据库时间是 naive，假设为 UTC
        last_time = last_collected_at.replace(tzinfo=timezone.utc)
    else:
        last_time = last_collected_at

    time_diff = (now - last_time).total_seconds()

    if time_diff <= 0:
        return

    # 计算差值（处理计数器重置的情况）
    reads_diff = max(0, curr_reads - last_reads)
    writes_diff = max(0, curr_writes - last_writes)
    read_sectors_diff = max(0, curr_read_sectors - last_read_sectors)
    write_sectors_diff = max(0, curr_write_sectors - last_write_sectors)

    # 计算速率
    current_metrics['disk_read_iops'] = round(reads_diff / time_diff, 2)
    current_metrics['disk_write_iops'] = round(writes_diff / time_diff, 2)
    current_metrics['disk_read_kb_per_sec'] = round((read_sectors_diff * 512 / 1024) / time_diff, 2)
    current_metrics['disk_write_kb_per_sec'] = round((write_sectors_diff * 512 / 1024) / time_diff, 2)


def _safe_float(value) -> float:
    """安全地将值转换为 float，失败返回 None"""
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (ValueError, TypeError):
        return None
