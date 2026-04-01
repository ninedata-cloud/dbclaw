import asyncio
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class OceanBaseConnector(DBConnector):
    """OceanBase database connector using aiomysql (MySQL-compatible mode)."""

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _get_conn_params(self):
        return dict(
            host=self.host,
            port=self.port,
            user=self.username,
            password=self.password or "",
            db=self.database or "",
        )

    async def _connect(self):
        import aiomysql
        return await aiomysql.connect(**self._get_conn_params(), connect_timeout=5)

    async def test_connection(self) -> str:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT VERSION()")
                row = await cur.fetchone()
                return row[0] if row else "unknown"
        finally:
            conn.close()

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                # Get server info
                try:
                    await cur.execute("SELECT * FROM oceanbase.gv$ob_servers LIMIT 10")
                    server_rows = await cur.fetchall()
                    server_count = len(server_rows)
                except Exception:
                    server_count = 0

                await cur.execute("SELECT CONNECTION_ID()")
                current_connection_id = (await cur.fetchone())[0]

                # Get process count for reference
                await cur.execute(
                    "SELECT "
                    "COUNT(*) as total, "
                    "SUM(CASE WHEN COMMAND != 'Sleep' THEN 1 ELSE 0 END) as active "
                    "FROM information_schema.PROCESSLIST "
                    "WHERE ID != %s",
                    (current_connection_id,)
                )
                process_stats = await cur.fetchone()
                process_count = process_stats[0] if process_stats else 0

                # Get global status
                await cur.execute("SHOW GLOBAL STATUS")
                rows = await cur.fetchall()
                status = {r[0]: r[1] for r in rows}

                max_connections: Optional[int] = None
                try:
                    await cur.execute("SHOW GLOBAL VARIABLES LIKE 'max_connections'")
                    max_conn_row = await cur.fetchone()
                    candidate = self._safe_int(max_conn_row[1]) if max_conn_row and len(max_conn_row) > 1 else 0
                    if 0 < candidate < 2147483647:
                        max_connections = candidate
                except Exception:
                    max_connections = None

                cache_hit_rate = self._calc_cache_hit_rate(status)

                visible_threads_running = int(process_stats[1] or 0) if process_stats else 0
                visible_threads_connected = int(process_stats[0] or 0) if process_stats else 0
                global_threads_running = int(status.get("Threads_running", 0))
                global_threads_connected = int(status.get("Threads_connected", 0))
                threads_running = max(visible_threads_running, max(global_threads_running - 1, 0))
                threads_connected = max(visible_threads_connected, global_threads_connected)

                uptime = max(self._safe_int(status.get("Uptime", 0)), 1)

                return {
                    "server_count": server_count,
                    "connections_active": threads_running,
                    "connections_total": threads_connected,
                    "max_connections": max_connections,
                    "process_count": process_count,
                    "threads_running": threads_running,
                    "threads_connected": threads_connected,
                    # 缓存命中率（百分比）。若无法计算则为 None，由前端展示为 --/空。
                    "cache_hit_rate": cache_hit_rate,
                    "buffer_pool_hit_rate": cache_hit_rate,
                    "queries_per_second": float(status.get("Queries", 0)),
                    "uptime": uptime,
                    "slow_queries": self._safe_int(status.get("Slow_queries", 0)),
                    "qps": round(self._safe_int(status.get("Queries", 0)) / uptime, 2),
                    "tps": round(
                        (self._safe_int(status.get("Com_commit", 0)) + self._safe_int(status.get("Com_rollback", 0)))
                        / uptime, 2
                    ),
                }
        finally:
            conn.close()

    def _calc_cache_hit_rate(self, status: Dict[str, Any]) -> Optional[float]:
        logical_reads = self._safe_int(status.get("Innodb_buffer_pool_read_requests", 0))
        physical_reads = self._safe_int(status.get("Innodb_buffer_pool_reads", 0))
        if logical_reads <= 0:
            # OceanBase MySQL 兼容模式下可能没有暴露 InnoDB 计数器；此时不展示假值。
            return None
        hit_rate = (1 - physical_reads / logical_reads) * 100
        return round(min(max(hit_rate, 0.0), 100.0), 2)

    async def get_variables(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SHOW GLOBAL VARIABLES")
                rows = await cur.fetchall()
                return {r[0]: r[1] for r in rows}
        finally:
            conn.close()

    async def get_process_list(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO "
                    "FROM information_schema.PROCESSLIST ORDER BY TIME DESC LIMIT 50"
                )
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
        except Exception:
            async with conn.cursor() as cur:
                await cur.execute("SHOW PROCESSLIST")
                rows = await cur.fetchall()
                return [
                    {"id": r[0], "user": r[1], "host": r[2], "db": r[3],
                     "command": r[4], "time": r[5], "state": r[6], "info": r[7]}
                    for r in rows
                ]
        finally:
            conn.close()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                try:
                    # OceanBase-specific SQL audit table
                    await cur.execute(
                        "SELECT request_time, elapsed_time, queue_time, execute_time, "
                        "affected_rows, return_rows, query_sql "
                        "FROM oceanbase.gv$sql_audit "
                        "WHERE elapsed_time > 1000000 "
                        "ORDER BY request_time DESC LIMIT 20"
                    )
                    rows = await cur.fetchall()
                    return [
                        {
                            "request_time": str(r[0]),
                            "elapsed_time_us": r[1],
                            "queue_time_us": r[2],
                            "execute_time_us": r[3],
                            "affected_rows": r[4],
                            "return_rows": r[5],
                            "sql": r[6]
                        }
                        for r in rows
                    ]
                except Exception:
                    return [{"message": "SQL audit table not accessible"}]
        finally:
            conn.close()

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        import time
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                start = time.time()
                await cur.execute(sql)
                elapsed = round((time.time() - start) * 1000, 2)

                if cur.description:
                    columns = [d[0] for d in cur.description]
                    fetched_rows = await cur.fetchmany(max_rows + 1)
                    truncated = len(fetched_rows) > max_rows
                    visible_rows = fetched_rows[:max_rows]
                    return {
                        "columns": columns,
                        "rows": [list(r) for r in visible_rows],
                        "row_count": len(visible_rows),
                        "execution_time_ms": elapsed,
                        "truncated": truncated,
                    }
                else:
                    row_count = cur.rowcount if cur.rowcount >= 0 else 0
                    await conn.commit()
                    return {
                        "columns": [],
                        "rows": [],
                        "row_count": row_count,
                        "execution_time_ms": elapsed,
                        "truncated": False,
                        "message": f"Query OK, {row_count} rows affected",
                    }
        finally:
            conn.close()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(f"EXPLAIN {sql}")
                columns = [d[0] for d in cur.description]
                rows = await cur.fetchall()
                return {
                    "columns": columns,
                    "rows": [list(r) for r in rows],
                }
        finally:
            conn.close()

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH, "
                    "AUTO_INCREMENT, ENGINE, TABLE_COLLATION "
                    "FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA = %s ORDER BY DATA_LENGTH DESC LIMIT 50",
                    (self.database,)
                )
                columns = [d[0] for d in cur.description]
                rows = await cur.fetchall()
                return [dict(zip(columns, r)) for r in rows]
        finally:
            conn.close()

    async def get_replication_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                try:
                    # OceanBase replica status
                    await cur.execute(
                        "SELECT tenant_name, database_name, table_name, "
                        "partition_idx, svr_ip, role, replica_type "
                        "FROM oceanbase.gv$table "
                        "LIMIT 100"
                    )
                    rows = await cur.fetchall()
                    if rows:
                        return {
                            "type": "oceanbase_replicas",
                            "replica_count": len(rows),
                            "replicas": [
                                {
                                    "tenant": r[0], "database": r[1], "table": r[2],
                                    "partition": r[3], "server": r[4], "role": r[5], "type": r[6]
                                }
                                for r in rows[:10]
                            ]
                        }
                except Exception:
                    pass
                return {"status": "not configured"}
        finally:
            conn.close()

    async def get_db_size(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT table_schema, "
                    "SUM(data_length + index_length) as total_size, "
                    "SUM(data_length) as data_size, "
                    "SUM(index_length) as index_size "
                    "FROM information_schema.tables "
                    f"WHERE table_schema = %s "
                    "GROUP BY table_schema",
                    (self.database,)
                )
                row = await cur.fetchone()
                if row:
                    return {
                        "database": row[0],
                        "total_size_bytes": int(row[1] or 0),
                        "data_size_bytes": int(row[2] or 0),
                        "index_size_bytes": int(row[3] or 0),
                    }
                return {}
        finally:
            conn.close()

    async def get_schemas(self) -> List[str]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
                    "WHERE SCHEMA_NAME NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys', 'oceanbase') "
                    "ORDER BY SCHEMA_NAME"
                )
                rows = await cur.fetchall()
                return [row[0] for row in rows]
        finally:
            conn.close()

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                target_schema = schema or self.database
                await cur.execute(
                    "SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_COMMENT "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s "
                    "ORDER BY TABLE_NAME",
                    (target_schema,)
                )
                rows = await cur.fetchall()
                return [
                    {
                        "name": row[0],
                        "schema": target_schema,
                        "type": row[1],
                        "engine": row[2],
                        "comment": row[3],
                    }
                    for row in rows
                ]
        finally:
            conn.close()

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                target_schema = schema or self.database
                await cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
                    "COLUMN_TYPE, COLUMN_KEY, EXTRA, COLUMN_COMMENT "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                    "ORDER BY ORDINAL_POSITION",
                    (target_schema, table)
                )
                rows = await cur.fetchall()
                return [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                        "full_type": row[4],
                        "key": row[5],
                        "extra": row[6],
                        "comment": row[7],
                    }
                    for row in rows
                ]
        finally:
            conn.close()


import aiomysql
