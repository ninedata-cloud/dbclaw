import asyncio
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class MySQLConnector(DBConnector):
    """MySQL database connector using aiomysql."""

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
        return await aiomysql.connect(**self._get_conn_params(), connect_timeout=10)

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
                await cur.execute("SHOW GLOBAL STATUS")
                rows = await cur.fetchall()
                status = {r[0]: r[1] for r in rows}

                await cur.execute("SELECT COUNT(*) FROM information_schema.PROCESSLIST")
                proc_count = (await cur.fetchone())[0]

                return {
                    "connections_active": proc_count,
                    "threads_running": int(status.get("Threads_running", 0)),
                    "threads_connected": int(status.get("Threads_connected", 0)),
                    "queries_per_second": float(status.get("Queries", 0)),
                    "bytes_received": int(status.get("Bytes_received", 0)),
                    "bytes_sent": int(status.get("Bytes_sent", 0)),
                    "uptime": int(status.get("Uptime", 0)),
                    "slow_queries": int(status.get("Slow_queries", 0)),
                    "buffer_pool_hit_rate": self._calc_bp_hit_rate(status),
                    "innodb_row_lock_waits": int(status.get("Innodb_row_lock_waits", 0)),
                    "table_locks_waited": int(status.get("Table_locks_waited", 0)),
                    "open_tables": int(status.get("Open_tables", 0)),
                    "qps": round(int(status.get("Queries", 0)) / max(int(status.get("Uptime", 1)), 1), 2),
                    "tps": round(
                        (int(status.get("Com_commit", 0)) + int(status.get("Com_rollback", 0)))
                        / max(int(status.get("Uptime", 1)), 1), 2
                    ),
                }
        finally:
            conn.close()

    def _calc_bp_hit_rate(self, status):
        reads = int(status.get("Innodb_buffer_pool_read_requests", 0))
        disk_reads = int(status.get("Innodb_buffer_pool_reads", 0))
        if reads == 0:
            return 100.0
        return round((1 - disk_reads / reads) * 100, 2)

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
                    await cur.execute(
                        "SELECT query_time, lock_time, rows_sent, rows_examined, sql_text "
                        "FROM mysql.slow_log ORDER BY start_time DESC LIMIT 20"
                    )
                    rows = await cur.fetchall()
                    return [
                        {"query_time": str(r[0]), "lock_time": str(r[1]),
                         "rows_sent": r[2], "rows_examined": r[3], "sql": r[4]}
                        for r in rows
                    ]
                except Exception:
                    return [{"message": "Slow query log table not accessible"}]
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
                    rows = await cur.fetchmany(max_rows)
                    total = cur.rowcount
                    return {
                        "columns": columns,
                        "rows": [list(r) for r in rows],
                        "row_count": len(rows),
                        "execution_time_ms": elapsed,
                        "truncated": total > max_rows if total >= 0 else False,
                    }
                else:
                    return {
                        "columns": [],
                        "rows": [],
                        "row_count": cur.rowcount,
                        "execution_time_ms": elapsed,
                        "message": f"Query OK, {cur.rowcount} rows affected",
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
                    await cur.execute("SHOW SLAVE STATUS")
                    row = await cur.fetchone()
                    if row and cur.description:
                        columns = [d[0] for d in cur.description]
                        return dict(zip(columns, row))
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
                    "WHERE SCHEMA_NAME NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
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

    async def get_index_stats(self) -> List[Dict[str, Any]]:
        """Get index usage statistics."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, CARDINALITY "
                    "FROM information_schema.STATISTICS "
                    f"WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
                    (self.database,)
                )
                rows = await cur.fetchall()
                return [{"table": r[0], "index": r[1], "non_unique": r[2], "seq": r[3], "column": r[4], "cardinality": r[5]} for r in rows]
        finally:
            conn.close()

    async def get_lock_waits(self) -> List[Dict[str, Any]]:
        """Get current lock waits."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT r.trx_id waiting_trx, r.trx_mysql_thread_id waiting_thread, "
                    "r.trx_query waiting_query, b.trx_id blocking_trx, b.trx_mysql_thread_id blocking_thread "
                    "FROM information_schema.INNODB_LOCK_WAITS w "
                    "JOIN information_schema.INNODB_TRX b ON b.trx_id = w.blocking_trx_id "
                    "JOIN information_schema.INNODB_TRX r ON r.trx_id = w.requesting_trx_id"
                )
                rows = await cur.fetchall()
                return [{"waiting_trx": r[0], "waiting_thread": r[1], "waiting_query": r[2], "blocking_trx": r[3], "blocking_thread": r[4]} for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    async def get_table_fragmentation(self) -> List[Dict[str, Any]]:
        """Get table fragmentation info."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT TABLE_NAME, DATA_FREE, DATA_LENGTH, "
                    "ROUND(DATA_FREE / (DATA_LENGTH + DATA_FREE) * 100, 2) as fragmentation_pct "
                    "FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA = %s AND DATA_FREE > 0 AND ENGINE = 'InnoDB' "
                    "ORDER BY DATA_FREE DESC LIMIT 20",
                    (self.database,)
                )
                rows = await cur.fetchall()
                return [{"table": r[0], "data_free": r[1], "data_length": r[2], "fragmentation_pct": float(r[3] or 0)} for r in rows]
        finally:
            conn.close()


import aiomysql
