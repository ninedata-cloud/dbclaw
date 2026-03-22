import asyncio
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class TiDBConnector(DBConnector):
    """TiDB database connector using aiomysql (MySQL-compatible)."""

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
                await cur.execute("SELECT TIDB_VERSION()")
                row = await cur.fetchone()
                return row[0] if row else "unknown"
        finally:
            conn.close()

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                # Get cluster info
                await cur.execute("SELECT * FROM INFORMATION_SCHEMA.CLUSTER_INFO")
                cluster_rows = await cur.fetchall()

                # Get active connections
                await cur.execute("SELECT COUNT(*) FROM information_schema.PROCESSLIST")
                proc_count = (await cur.fetchone())[0]

                # Get global status
                await cur.execute("SHOW GLOBAL STATUS")
                rows = await cur.fetchall()
                status = {r[0]: r[1] for r in rows}

                return {
                    "cluster_nodes": len(cluster_rows),
                    "connections_active": proc_count,
                    "threads_running": int(status.get("Threads_running", 0)),
                    "threads_connected": int(status.get("Threads_connected", 0)),
                    "queries_per_second": float(status.get("Queries", 0)),
                    "uptime": int(status.get("Uptime", 0)),
                    "slow_queries": int(status.get("Slow_queries", 0)),
                    "qps": round(int(status.get("Queries", 0)) / max(int(status.get("Uptime", 1)), 1), 2),
                    "tps": round(
                        (int(status.get("Com_commit", 0)) + int(status.get("Com_rollback", 0)))
                        / max(int(status.get("Uptime", 1)), 1), 2
                    ),
                }
        finally:
            conn.close()

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
                    # TiDB-specific slow query table
                    await cur.execute(
                        "SELECT Query_time, Parse_time, Compile_time, Process_time, "
                        "Wait_time, Query "
                        "FROM INFORMATION_SCHEMA.SLOW_QUERY "
                        "ORDER BY Time DESC LIMIT 20"
                    )
                    rows = await cur.fetchall()
                    return [
                        {
                            "query_time": str(r[0]),
                            "parse_time": str(r[1]),
                            "compile_time": str(r[2]),
                            "process_time": str(r[3]),
                            "wait_time": str(r[4]),
                            "sql": r[5]
                        }
                        for r in rows
                    ]
                except Exception:
                    return [{"message": "Slow query table not accessible"}]
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
                # TiDB supports EXPLAIN ANALYZE
                await cur.execute(f"EXPLAIN ANALYZE {sql}")
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
                    # TiDB region peer status
                    await cur.execute(
                        "SELECT REGION_ID, STORE_ID, IS_LEADER, STATUS "
                        "FROM INFORMATION_SCHEMA.TIKV_REGION_PEERS "
                        "LIMIT 100"
                    )
                    rows = await cur.fetchall()
                    if rows:
                        return {
                            "type": "tikv_regions",
                            "region_count": len(rows),
                            "regions": [
                                {"region_id": r[0], "store_id": r[1], "is_leader": r[2], "status": r[3]}
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


import aiomysql
