import asyncio
import logging
import platform

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 3.0  # 整体超时秒数


async def check_network(host: str) -> bool:
    """
    使用系统 ping 命令检测网络连通性。

    Returns:
        True 表示可达，False 表示不可达或超时或异常
    """
    proc = None
    try:
        # macOS/Linux: ping -c 1 -W 2 <host>
        # Windows: ping -n 1 -w 2000 <host>
        if platform.system().lower() == "windows":
            args = ["ping", "-n", "1", "-w", "2000", host]
        else:
            args = ["ping", "-c", "1", "-W", "2", host]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=_PROBE_TIMEOUT)
        return proc.returncode == 0

    except asyncio.TimeoutError:
        logger.warning(f"Network probe timeout for host: {host}")
        if proc is not None:
            try:
                proc.kill()
            except Exception as e:
                logger.debug("Failed to kill ping process: %s", e)
        return False
    except Exception as e:
        logger.warning(f"Network probe error for host {host}: {e}")
        return False
