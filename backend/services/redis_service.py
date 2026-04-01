import time
from typing import Any, Dict, List
from backend.services.db_connector import DBConnector


class RedisConnector(DBConnector):
    """Redis connector using redis-py async."""

    async def _connect(self):
        import redis.asyncio as aioredis
        client = aioredis.Redis(
            host=self.host, port=self.port,
            password=self.password or None,
            db=int(self.database or 0),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        return client

    async def test_connection(self) -> str:
        client = await self._connect()
        try:
            info = await client.info("server")
            return f"Redis {info.get('redis_version', 'unknown')}"
        finally:
            await client.aclose()

    async def get_status(self) -> Dict[str, Any]:
        client = await self._connect()
        try:
            info = await client.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_bytes": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak": info.get("used_memory_peak_human", "0B"),
                "total_connections_received": info.get("total_connections_received", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calc_hit_rate(info),
                "evicted_keys": info.get("evicted_keys", 0),
                "blocked_clients": info.get("blocked_clients", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "used_cpu_sys": info.get("used_cpu_sys", 0),
                "input_kbps": info.get("instantaneous_input_kbps", 0),
                "output_kbps": info.get("instantaneous_output_kbps", 0),
            }
        finally:
            await client.aclose()

    def _calc_hit_rate(self, info):
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        if total == 0:
            return 100.0
        return round((hits / total) * 100, 2)

    async def get_variables(self) -> Dict[str, Any]:
        client = await self._connect()
        try:
            config = await client.config_get("*")
            return config
        finally:
            await client.aclose()

    async def get_process_list(self) -> List[Dict[str, Any]]:
        client = await self._connect()
        try:
            clients = await client.client_list()
            return [
                {
                    "id": c.get("id"),
                    "addr": c.get("addr"),
                    "fd": c.get("fd"),
                    "age": c.get("age"),
                    "idle": c.get("idle"),
                    "db": c.get("db"),
                    "cmd": c.get("cmd"),
                }
                for c in clients[:50]
            ]
        finally:
            await client.aclose()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        client = await self._connect()
        try:
            slowlogs = await client.slowlog_get(20)
            return [
                {
                    "id": entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None),
                    "duration_us": entry.get("duration") if isinstance(entry, dict) else getattr(entry, "duration", None),
                    "command": str(entry.get("command", "")) if isinstance(entry, dict) else str(getattr(entry, "command", "")),
                    "start_time": str(entry.get("start_time", "")) if isinstance(entry, dict) else str(getattr(entry, "start_time", "")),
                }
                for entry in slowlogs
            ]
        finally:
            await client.aclose()

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        """Execute a Redis command."""
        client = await self._connect()
        try:
            parts = sql.strip().split()
            if not parts:
                return {"columns": ["error"], "rows": [["Empty command"]], "row_count": 1, "execution_time_ms": 0}

            start = time.time()
            result = await client.execute_command(*parts)
            elapsed = round((time.time() - start) * 1000, 2)

            if isinstance(result, list):
                return {
                    "columns": ["value"],
                    "rows": [[str(v)] for v in result[:max_rows]],
                    "row_count": len(result),
                    "execution_time_ms": elapsed,
                    "truncated": len(result) > max_rows,
                }
            return {
                "columns": ["result"],
                "rows": [[str(result)]],
                "row_count": 1,
                "execution_time_ms": elapsed,
            }
        finally:
            await client.aclose()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        return {"message": "EXPLAIN not supported for Redis. Use SLOWLOG for query analysis."}

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        client = await self._connect()
        try:
            info = await client.info("keyspace")
            stats = []
            for db_key, db_info in info.items():
                if isinstance(db_info, dict):
                    stats.append({
                        "database": db_key,
                        "keys": db_info.get("keys", 0),
                        "expires": db_info.get("expires", 0),
                        "avg_ttl": db_info.get("avg_ttl", 0),
                    })
            return stats
        finally:
            await client.aclose()

    async def get_replication_status(self) -> Dict[str, Any]:
        client = await self._connect()
        try:
            info = await client.info("replication")
            return {
                "role": info.get("role", "unknown"),
                "connected_slaves": info.get("connected_slaves", 0),
                "master_host": info.get("master_host"),
                "master_port": info.get("master_port"),
                "master_link_status": info.get("master_link_status"),
            }
        finally:
            await client.aclose()

    async def get_db_size(self) -> Dict[str, Any]:
        client = await self._connect()
        try:
            dbsize = await client.dbsize()
            info = await client.info("memory")
            return {
                "database": self.database or "0",
                "key_count": dbsize,
                "used_memory_bytes": info.get("used_memory", 0),
            }
        finally:
            await client.aclose()
