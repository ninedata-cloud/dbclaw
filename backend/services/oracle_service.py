import time
from typing import Any, Dict, List
from backend.services.db_connector import DBConnector


class OracleConnector(DBConnector):
    """Oracle database connector using python-oracledb."""

    async def _connect(self):
        import oracledb
        # Use thin mode (no Oracle Client required)
        oracledb.init_oracle_client(lib_dir=None)

        # Build connection string
        dsn = f"{self.host}:{self.port}/{self.database or 'ORCL'}"

        # Create connection pool for better performance
        connection = await oracledb.connect_async(
            user=self.username,
            password=self.password or "",
            dsn=dsn,
            encoding="UTF-8"
        )
        return connection

    async def test_connection(self) -> str:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            result = await cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
            row = await result.fetchone()
            await cursor.close()
            return row[0] if row else "unknown"
        finally:
            await conn.close()

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()

            # Get session count
            await cursor.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) as active "
                "FROM v$session WHERE type = 'USER'"
            )
            session_stats = await cursor.fetchone()

            # Get database size
            await cursor.execute(
                "SELECT SUM(bytes) as total_size FROM dba_data_files"
            )
            size_row = await cursor.fetchone()

            # Get cache hit ratio
            await cursor.execute(
                "SELECT (1 - (phy.value / (db.value + cons.value))) * 100 as hit_ratio "
                "FROM v$sysstat phy, v$sysstat db, v$sysstat cons "
                "WHERE phy.name = 'physical reads' "
                "AND db.name = 'db block gets' "
                "AND cons.name = 'consistent gets'"
            )
            cache_row = await cursor.fetchone()

            await cursor.close()

            return {
                "connections_total": session_stats[0] if session_stats else 0,
                "connections_active": session_stats[1] if session_stats else 0,
                "db_size_bytes": size_row[0] if size_row and size_row[0] else 0,
                "cache_hit_rate": round(cache_row[0], 2) if cache_row and cache_row[0] else 0,
            }
        finally:
            await conn.close()

    async def get_variables(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute("SELECT name, value FROM v$parameter ORDER BY name")
            rows = await cursor.fetchall()
            await cursor.close()
            return {row[0]: row[1] for row in rows}
        finally:
            await conn.close()

    async def get_process_list(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT s.sid, s.serial#, s.username, s.status, s.osuser, "
                "s.machine, s.program, s.sql_id, s.logon_time, "
                "sq.sql_text "
                "FROM v$session s "
                "LEFT JOIN v$sql sq ON s.sql_id = sq.sql_id "
                "WHERE s.type = 'USER' "
                "ORDER BY s.logon_time DESC "
                "FETCH FIRST 50 ROWS ONLY"
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            await cursor.close()

            return [dict(zip(columns, row)) for row in rows]
        finally:
            await conn.close()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT sql_id, sql_text, executions, "
                "elapsed_time / 1000000 as elapsed_time_sec, "
                "cpu_time / 1000000 as cpu_time_sec, "
                "disk_reads, buffer_gets, rows_processed "
                "FROM v$sql "
                "WHERE executions > 0 "
                "ORDER BY elapsed_time / executions DESC "
                "FETCH FIRST 20 ROWS ONLY"
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            await cursor.close()

            return [dict(zip(columns, row)) for row in rows]
        finally:
            await conn.close()

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            start = time.time()
            await cursor.execute(sql)
            rows = await cursor.fetchmany(max_rows)
            elapsed = round((time.time() - start) * 1000, 2)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            row_count = cursor.rowcount if cursor.rowcount > 0 else len(rows)

            await cursor.close()

            return {
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": row_count,
                "execution_time_ms": elapsed,
                "truncated": len(rows) >= max_rows,
            }
        finally:
            await conn.close()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()

            # Set statement ID for explain plan
            stmt_id = f"EXPLAIN_{int(time.time())}"

            # Execute explain plan
            await cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {sql}")

            # Get the plan
            await cursor.execute(
                f"SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', '{stmt_id}', 'ALL'))"
            )
            rows = await cursor.fetchall()

            # Clean up
            await cursor.execute(f"DELETE FROM plan_table WHERE statement_id = '{stmt_id}'")
            await conn.commit()
            await cursor.close()

            return {"plan": [row[0] for row in rows]}
        finally:
            await conn.close()

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT owner, table_name, num_rows, blocks, "
                "avg_row_len, last_analyzed "
                "FROM dba_tables "
                "WHERE owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP') "
                "ORDER BY num_rows DESC NULLS LAST "
                "FETCH FIRST 50 ROWS ONLY"
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            await cursor.close()

            return [dict(zip(columns, row)) for row in rows]
        finally:
            await conn.close()

    async def get_replication_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()

            # Check if Data Guard is configured
            await cursor.execute(
                "SELECT database_role, protection_mode, protection_level "
                "FROM v$database"
            )
            row = await cursor.fetchone()

            if row and row[0] != 'PRIMARY':
                # Get standby status
                await cursor.execute(
                    "SELECT process, status, thread#, sequence# "
                    "FROM v$managed_standby"
                )
                standby_rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                await cursor.close()

                return {
                    "role": row[0],
                    "protection_mode": row[1],
                    "protection_level": row[2],
                    "standby_processes": [dict(zip(columns, r)) for r in standby_rows]
                }

            await cursor.close()
            return {"role": row[0] if row else "UNKNOWN", "status": "not configured"}
        finally:
            await conn.close()

    async def get_db_size(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT SUM(bytes) as data_size FROM dba_data_files "
                "UNION ALL "
                "SELECT SUM(bytes) as log_size FROM v$log"
            )
            rows = await cursor.fetchall()
            await cursor.close()

            data_size = rows[0][0] if rows and rows[0][0] else 0
            log_size = rows[1][0] if len(rows) > 1 and rows[1][0] else 0

            return {
                "data_size_bytes": data_size,
                "log_size_bytes": log_size,
                "total_size_bytes": data_size + log_size,
            }
        finally:
            await conn.close()
