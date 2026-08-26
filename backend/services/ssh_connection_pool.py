import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager

import paramiko
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.host import Host
from backend.config import get_settings
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


@dataclass
class SSHConnection:
    """SSH连接包装器"""
    client: paramiko.SSHClient
    host_id: int
    last_used: float
    is_healthy: bool = True
    
    def mark_used(self):
        """标记连接被使用"""
        self.last_used = time.time()
    
    def is_expired(self, max_idle_seconds: int = 300) -> bool:
        """检查连接是否过期（默认5分钟）"""
        return time.time() - self.last_used > max_idle_seconds


@dataclass(frozen=True)
class SSHHostConfig:
    id: int
    name: str
    host: str
    port: int
    username: str
    auth_type: str
    password_encrypted: Optional[str]
    private_key_encrypted: Optional[str]

    @classmethod
    def from_host(cls, host: Host) -> "SSHHostConfig":
        return cls(
            id=host.id,
            name=host.name,
            host=host.host,
            port=host.port,
            username=host.username,
            auth_type=host.auth_type,
            password_encrypted=host.password_encrypted,
            private_key_encrypted=host.private_key_encrypted,
        )


@dataclass
class SSHFailureState:
    failures: int
    next_retry_at: float
    detail: str


class SSHConnectionPool:
    """SSH连接池管理器"""
    
    def __init__(self, max_idle_seconds: int = 300, health_check_interval: int = 60):
        """
        初始化连接池
        
        Args:
            max_idle_seconds: 最大空闲时间（秒），超过后关闭连接
            health_check_interval: 健康检查间隔（秒）
        """
        self._connections: Dict[int, SSHConnection] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._max_idle_seconds = max_idle_seconds
        self._health_check_interval = health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._failure_states: Dict[int, SSHFailureState] = {}
        settings = get_settings()
        self._failure_backoff_base = max(1.0, settings.ssh_failure_backoff_base_seconds)
        self._failure_backoff_max = max(
            self._failure_backoff_base,
            settings.ssh_failure_backoff_max_seconds,
        )
        
    async def start(self):
        """启动连接池和健康检查任务"""
        if self._running:
            return
        
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("SSH connection pool started")
    
    async def stop(self):
        """停止连接池并关闭所有连接"""
        self._running = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有连接
        for host_id, conn in list(self._connections.items()):
            try:
                conn.client.close()
                logger.info(f"Closed SSH connection for host {host_id}")
            except Exception as e:
                logger.warning(f"Error closing SSH connection for host {host_id}: {e}")
        
        self._connections.clear()
        self._locks.clear()
        self._failure_states.clear()
        logger.info("SSH connection pool stopped")
    
    def _get_lock(self, host_id: int) -> asyncio.Lock:
        """获取主机的锁"""
        if host_id not in self._locks:
            self._locks[host_id] = asyncio.Lock()
        return self._locks[host_id]
    
    async def _create_connection(self, db: AsyncSession, host_id: int) -> Optional[SSHConnection]:
        """Load a host record and create an SSH connection."""
        try:
            result = await db.execute(
                select(Host).where(Host.id == host_id)
            )
            host = result.scalar_one_or_none()
            if not host:
                logger.warning(f"Host {host_id} not found")
                return None

            return await self._create_connection_from_config(SSHHostConfig.from_host(host))
        except Exception as e:
            logger.error(f"Failed to load SSH configuration for host {host_id}: {e}")
            return None

    async def _create_connection_from_config(self, host: SSHHostConfig) -> Optional[SSHConnection]:
        """Create SSH transport from a detached, immutable host configuration."""
        ssh_client = paramiko.SSHClient()
        try:
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            loop = asyncio.get_running_loop()
            common_connect_args = {
                "hostname": host.host,
                "port": host.port,
                "username": host.username,
                "timeout": 10,
                "banner_timeout": 10,
                "auth_timeout": 10,
            }

            if host.auth_type == 'agent':
                await loop.run_in_executor(
                    None,
                    lambda: ssh_client.connect(
                        **common_connect_args,
                        allow_agent=True,
                        look_for_keys=True,
                    )
                )
            elif host.auth_type == 'password':
                password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
                await loop.run_in_executor(
                    None,
                    lambda: ssh_client.connect(
                        **common_connect_args,
                        password=password,
                        allow_agent=False,
                        look_for_keys=False,
                    )
                )
            else:
                private_key_str = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
                if private_key_str:
                    from io import StringIO
                    key_file = StringIO(private_key_str)
                    try:
                        private_key = paramiko.RSAKey.from_private_key(key_file)
                    except Exception as e:
                        logger.debug("RSA key parse failed, trying Ed25519: %s", e)
                        key_file.seek(0)
                        try:
                            private_key = paramiko.Ed25519Key.from_private_key(key_file)
                        except Exception as e:
                            logger.debug("Ed25519 key parse failed, trying ECDSA: %s", e)
                            key_file.seek(0)
                            private_key = paramiko.ECDSAKey.from_private_key(key_file)
                    await loop.run_in_executor(
                        None,
                        lambda: ssh_client.connect(
                            **common_connect_args,
                            pkey=private_key,
                            allow_agent=False,
                            look_for_keys=False,
                        )
                    )
                else:
                    logger.warning(f"No private key found for host {host.id}")
                    ssh_client.close()
                    return None

            conn = SSHConnection(
                client=ssh_client,
                host_id=host.id,
                last_used=time.time(),
                is_healthy=True
            )

            logger.info(f"Created SSH connection for host {host.id} ({host.host}:{host.port})")
            return conn

        except Exception as e:
            ssh_client.close()
            logger.error(f"Failed to create SSH connection for host {host.id}: {e}")
            return None

    def _sync_check_connection_health(self, conn: SSHConnection) -> bool:
        """同步健康检查（在线程池中执行）"""
        try:
            transport = conn.client.get_transport()
            if transport is None or not transport.is_active():
                return False
            return True
        except Exception:
            return False

    async def _check_connection_health(self, conn: SSHConnection) -> bool:
        """检查连接健康状态（异步）"""
        loop = asyncio.get_event_loop()
        try:
            # 在线程池中执行同步检查，避免阻塞事件循环
            is_active = await loop.run_in_executor(
                None,
                self._sync_check_connection_health,
                conn
            )
            return is_active
        except Exception as e:
            logger.debug(f"Health check failed for host {conn.host_id}: {e}")
            return False

    def mark_connection_unhealthy(self, host_id: int):
        """标记连接为不健康（用于超时等异常情况）"""
        if host_id in self._connections:
            self._connections[host_id].is_healthy = False
            logger.info(f"Marked SSH connection as unhealthy for host {host_id}")

    async def _health_check_loop(self):
        """定期健康检查循环"""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)

                for host_id, conn in list(self._connections.items()):
                    # 检查是否过期
                    if conn.is_expired(self._max_idle_seconds):
                        logger.info(f"Closing expired SSH connection for host {host_id}")
                        async with self._get_lock(host_id):
                            try:
                                conn.client.close()
                            except Exception as e:
                                logger.debug("Error closing SSH connection during health check: %s", e)
                            del self._connections[host_id]
                        continue

                    # 健康检查（异步）
                    is_healthy = await self._check_connection_health(conn)
                    if not is_healthy:
                        logger.warning(f"SSH connection for host {host_id} is unhealthy, marking for reconnection")
                        conn.is_healthy = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
    
    def _record_connection_failure(self, host_id: int, detail: str) -> None:
        previous = self._failure_states.get(host_id)
        failures = (previous.failures + 1) if previous else 1
        exponent = min(failures - 1, 30)
        delay = min(self._failure_backoff_max, self._failure_backoff_base * (2 ** exponent))
        self._failure_states[host_id] = SSHFailureState(
            failures=failures,
            next_retry_at=time.monotonic() + delay,
            detail=detail,
        )
        logger.warning(
            "SSH reconnect for host %s will be retried in %.0f seconds after %s consecutive failures",
            host_id,
            delay,
            failures,
        )

    def _check_retry_backoff(self, host_id: int) -> None:
        state = self._failure_states.get(host_id)
        if not state:
            return
        remaining = state.next_retry_at - time.monotonic()
        if remaining > 0:
            raise ConnectionError(
                f"SSH retry backoff active for host {host_id} ({remaining:.0f}s remaining): {state.detail}"
            )

    async def _acquire_connection(
        self,
        host_id: int,
        creator: Callable[[], Awaitable[Optional[SSHConnection]]],
        *,
        enforce_backoff: bool,
    ) -> SSHConnection:
        lock = self._get_lock(host_id)
        async with lock:
            conn = self._connections.get(host_id)
            if conn is None or not conn.is_healthy:
                if conn is not None:
                    try:
                        conn.client.close()
                    except Exception as e:
                        logger.debug("Error closing unhealthy SSH connection: %s", e)

                if enforce_backoff:
                    self._check_retry_backoff(host_id)

                conn = await creator()
                if conn is None:
                    self._record_connection_failure(host_id, "connection creation failed")
                    raise ConnectionError(f"Failed to create SSH connection for host {host_id}")

                self._connections[host_id] = conn
                self._failure_states.pop(host_id, None)

            conn.mark_used()
            return conn

    @asynccontextmanager
    async def _yield_connection(self, conn: SSHConnection):
        try:
            yield conn.client
        except Exception as e:
            logger.warning(f"Error using SSH connection for host {conn.host_id}: {e}")
            conn.is_healthy = False
            raise

    @asynccontextmanager
    async def get_connection(self, db: AsyncSession, host_id: int):
        """Get an SSH connection for request-driven operations.

        Request paths bypass collector backoff so an operator can immediately
        verify a host after correcting its configuration.
        """
        conn = await self._acquire_connection(
            host_id,
            lambda: self._create_connection(db, host_id),
            enforce_backoff=False,
        )
        async with self._yield_connection(conn) as client:
            yield client

    @asynccontextmanager
    async def get_collector_connection(self, host: SSHHostConfig):
        """Get an SSH connection without holding a metadata DB session."""
        conn = await self._acquire_connection(
            host.id,
            lambda: self._create_connection_from_config(host),
            enforce_backoff=True,
        )
        async with self._yield_connection(conn) as client:
            yield client
    
    def get_stats(self) -> Dict[str, any]:
        """获取连接池统计信息"""
        return {
            "total_connections": len(self._connections),
            "healthy_connections": sum(1 for c in self._connections.values() if c.is_healthy),
            "backoff_hosts": len(self._failure_states),
            "connections": {
                host_id: {
                    "is_healthy": conn.is_healthy,
                    "last_used": conn.last_used,
                    "idle_seconds": time.time() - conn.last_used
                }
                for host_id, conn in self._connections.items()
            }
        }


# 全局连接池实例
_ssh_pool: Optional[SSHConnectionPool] = None


def get_ssh_pool() -> SSHConnectionPool:
    """获取全局SSH连接池实例"""
    global _ssh_pool
    if _ssh_pool is None:
        _ssh_pool = SSHConnectionPool()
    return _ssh_pool


async def start_ssh_pool():
    """启动SSH连接池"""
    pool = get_ssh_pool()
    await pool.start()


async def stop_ssh_pool():
    """停止SSH连接池"""
    global _ssh_pool
    if _ssh_pool:
        await _ssh_pool.stop()
        _ssh_pool = None
