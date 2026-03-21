import time
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class OracleConnector(DBConnector):
    """Oracle database connector using python-oracledb."""

    def __init__(self, host: str, port: int, username: str = None,
                 password: str = None, database: str = None,
                 oracle_conn_mode: str = None, **kwargs):
        super().__init__(host=host, port=port, username=username,
                         password=password, database=database)
        self.oracle_conn_mode = oracle_conn_mode or 'default'

    async def _connect(self):
        import oracledb
        dsn = f"{self.host}:{self.port}/{self.database or 'ORCL'}"
        mode = 0  # oracledb.AUTH_MODE_DEFAULT
        if self.oracle_conn_mode == 'sysdba':
            mode = oracledb.AUTH_MODE_SYSDBA
        elif self.oracle_conn_mode == 'sysoper':
            mode = oracledb.AUTH_MODE_SYSOPER
        connection = await oracledb.connect_async(
            user=self.username,
            password=self.password or "",
            dsn=dsn,
            mode=mode
        )
        return connection

    async def test_connection(self) -> str:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
            row = await cursor.fetchone()
            cursor.close()
            return row[0] if row else "unknown"
        finally:
            await conn.close()

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()

            # 1. 会话统计
            await cursor.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) as active, "
                "SUM(CASE WHEN status = 'INACTIVE' THEN 1 ELSE 0 END) as inactive, "
                "SUM(CASE WHEN wait_class != 'Idle' AND status = 'ACTIVE' THEN 1 ELSE 0 END) as waiting "
                "FROM v$session WHERE type = 'USER'"
            )
            session_stats = await cursor.fetchone()

            # 2. 系统统计（累积值，用于计算速率）
            await cursor.execute(
                "SELECT name, value FROM v$sysstat "
                "WHERE name IN ("
                "'user calls', 'user commits', 'user rollbacks', "
                "'physical reads', 'physical writes', "
                "'db block gets', 'consistent gets', "
                "'redo writes', 'parse count (total)', "
                "'execute count', 'bytes sent via SQL*Net to client', "
                "'bytes received via SQL*Net from client')"
            )
            sysstat = {}
            for row in await cursor.fetchall():
                sysstat[row[0]] = int(row[1]) if row[1] is not None else 0

            # 3. 数据库大小
            await cursor.execute(
                "SELECT SUM(bytes) as total_size FROM dba_data_files"
            )
            size_row = await cursor.fetchone()

            # 4. 缓存命中率
            db_block_gets = sysstat.get('db block gets', 0)
            consistent_gets = sysstat.get('consistent gets', 0)
            physical_reads = sysstat.get('physical reads', 0)
            logical_reads = db_block_gets + consistent_gets
            cache_hit_rate = 0.0
            if logical_reads > 0:
                cache_hit_rate = round((1 - physical_reads / logical_reads) * 100, 2)

            # 5. 启动时间
            await cursor.execute(
                "SELECT startup_time FROM v$instance"
            )
            startup_row = await cursor.fetchone()

            uptime = 0
            boot_time = None
            if startup_row and startup_row[0]:
                from datetime import datetime, timezone
                boot_time = startup_row[0]
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                uptime = int((now_utc - boot_time).total_seconds())

            # 6. 锁等待数
            await cursor.execute(
                "SELECT COUNT(*) FROM v$session WHERE blocking_session IS NOT NULL AND type = 'USER'"
            )
            lock_row = await cursor.fetchone()

            # 7. 最长活跃事务时间（秒）
            await cursor.execute(
                "SELECT MAX((SYSDATE - start_date) * 86400) as seconds "
                "FROM v$transaction"
            )
            longest_tx_row = await cursor.fetchone()

            cursor.close()

            return {
                # 连接指标
                "connections_active": session_stats[1] if session_stats else 0,
                "connections_total": session_stats[0] if session_stats else 0,
                "connections_idle": session_stats[2] if session_stats else 0,
                "connections_waiting": session_stats[3] if session_stats else 0,
                "lock_waiting": lock_row[0] if lock_row else 0,
                "longest_transaction_sec": int(longest_tx_row[0]) if longest_tx_row and longest_tx_row[0] else 0,
                # 吞吐量（累积值，由 normalizer 计算速率）
                "user_calls": sysstat.get('user calls', 0),
                "user_commits": sysstat.get('user commits', 0),
                "user_rollbacks": sysstat.get('user rollbacks', 0),
                "execute_count": sysstat.get('execute count', 0),
                "parse_count": sysstat.get('parse count (total)', 0),
                # 磁盘 IO（累积值）
                "physical_reads": sysstat.get('physical reads', 0),
                "physical_writes": sysstat.get('physical writes', 0),
                "redo_writes": sysstat.get('redo writes', 0),
                # 网络 IO（累积字节数）
                "network_bytes_sent": sysstat.get('bytes sent via SQL*Net to client', 0),
                "network_bytes_received": sysstat.get('bytes received via SQL*Net from client', 0),
                # 缓存
                "cache_hit_rate": cache_hit_rate,
                # 数据库大小
                "db_size_bytes": size_row[0] if size_row and size_row[0] else 0,
                # 运行时间
                "uptime": uptime,
                "boot_time": boot_time.isoformat() if boot_time else None,
            }
        finally:
            await conn.close()

    async def get_variables(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute("SELECT name, value FROM v$parameter ORDER BY name")
            rows = await cursor.fetchall()
            cursor.close()
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
            cursor.close()

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
            cursor.close()

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

            cursor.close()

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

            stmt_id = f"EXPLAIN_{int(time.time())}"

            await cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {sql}")

            await cursor.execute(
                f"SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', '{stmt_id}', 'ALL'))"
            )
            rows = await cursor.fetchall()

            await cursor.execute(f"DELETE FROM plan_table WHERE statement_id = '{stmt_id}'")
            await conn.commit()
            cursor.close()

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
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]
        finally:
            await conn.close()

    async def get_replication_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()

            await cursor.execute(
                "SELECT database_role, protection_mode, protection_level "
                "FROM v$database"
            )
            row = await cursor.fetchone()

            if row and row[0] != 'PRIMARY':
                await cursor.execute(
                    "SELECT process, status, thread#, sequence# "
                    "FROM v$managed_standby"
                )
                standby_rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                cursor.close()

                return {
                    "role": row[0],
                    "protection_mode": row[1],
                    "protection_level": row[2],
                    "standby_processes": [dict(zip(columns, r)) for r in standby_rows]
                }

            cursor.close()
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
            cursor.close()

            data_size = rows[0][0] if rows and rows[0][0] else 0
            log_size = rows[1][0] if len(rows) > 1 and rows[1][0] else 0

            return {
                "data_size_bytes": data_size,
                "log_size_bytes": log_size,
                "total_size_bytes": data_size + log_size,
            }
        finally:
            await conn.close()

    async def get_schemas(self) -> List[str]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT username FROM all_users "
                "WHERE username NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'APPQOSSYS', "
                "'WMSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'ORDSYS', 'MDSYS', 'OLAPSYS') "
                "ORDER BY username"
            )
            rows = await cursor.fetchall()
            cursor.close()
            return [row[0] for row in rows]
        finally:
            await conn.close()

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            target_schema = schema or self.username.upper()
            await cursor.execute(
                "SELECT table_name, owner, tablespace_name "
                "FROM all_tables "
                "WHERE owner = :schema "
                "ORDER BY table_name",
                {"schema": target_schema}
            )
            rows = await cursor.fetchall()
            cursor.close()
            return [
                {
                    "name": row[0],
                    "schema": row[1],
                    "tablespace": row[2],
                    "type": "TABLE",
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            target_schema = schema or self.username.upper()
            await cursor.execute(
                "SELECT column_name, data_type, nullable, data_length, "
                "data_precision, data_scale, data_default "
                "FROM all_tab_columns "
                "WHERE owner = :schema AND table_name = :table "
                "ORDER BY column_id",
                {"schema": target_schema, "table": table.upper()}
            )
            rows = await cursor.fetchall()
            cursor.close()
            return [
                {
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "Y",
                    "length": row[3],
                    "precision": row[4],
                    "scale": row[5],
                    "default": row[6],
                }
                for row in rows
            ]
        finally:
            await conn.close()
