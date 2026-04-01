import time
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class SQLServerConnector(DBConnector):
    """SQL Server connector using pyodbc."""

    def _get_conn_string(self):
        driver = "{ODBC Driver 18 for SQL Server}"
        s = (f"DRIVER={driver};SERVER={self.host},{self.port};"
             f"DATABASE={self.database or 'master'};"
             f"UID={self.username};PWD={self.password};"
             f"TrustServerCertificate=yes;Connection Timeout=5")
        return s

    def _connect(self):
        import pyodbc
        conn = pyodbc.connect(self._get_conn_string(), autocommit=True)

        # Add output converter for sql_variant type (ODBC type -16)
        # This handles columns like sys.configurations.value
        def handle_sql_variant(value):
            return str(value) if value is not None else None

        conn.add_output_converter(-16, handle_sql_variant)

        return conn

    async def test_connection(self) -> str:
        import asyncio
        def _test():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT @@VERSION")
                row = cursor.fetchone()
                return row[0].split('\n')[0] if row else "unknown"
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _test)

    async def get_status(self) -> Dict[str, Any]:
        import asyncio
        def _status():
            conn = self._connect()
            try:
                cursor = conn.cursor()

                # 1. 连接/会话指标
                cursor.execute(
                    "SELECT "
                    "(SELECT count(*) FROM sys.dm_exec_sessions) as total_sessions, "
                    "(SELECT count(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1) as user_sessions, "
                    "(SELECT count(*) FROM sys.dm_exec_requests WHERE status = 'running') as active_requests, "
                    "(SELECT count(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1 AND status = 'sleeping') as idle_sessions, "
                    "(SELECT count(*) FROM sys.dm_exec_requests WHERE blocking_session_id <> 0) as blocked_requests, "
                    "(SELECT sqlserver_start_time FROM sys.dm_os_sys_info) as start_time, "
                    "@@SPID as current_session_id"
                )
                row = cursor.fetchone()

                total_sessions = row[0] if row else 0
                user_sessions = row[1] if row else 0
                active_requests = row[2] if row else 0
                idle_sessions = row[3] if row else 0
                blocked_requests = row[4] if row else 0
                current_session_id = row[6] if row else None

                if current_session_id is not None:
                    cursor.execute(
                        "SELECT "
                        "SUM(CASE WHEN is_user_process = 1 AND session_id <> ? THEN 1 ELSE 0 END) as total_user_sessions, "
                        "SUM(CASE WHEN is_user_process = 1 AND status = 'sleeping' AND session_id <> ? THEN 1 ELSE 0 END) as idle_user_sessions "
                        "FROM sys.dm_exec_sessions",
                        current_session_id, current_session_id
                    )
                    visible_row = cursor.fetchone()
                    visible_user_sessions = visible_row[0] if visible_row and visible_row[0] is not None else 0
                    visible_idle_sessions = visible_row[1] if visible_row and visible_row[1] is not None else 0
                else:
                    visible_user_sessions = user_sessions
                    visible_idle_sessions = idle_sessions

                cursor.execute(
                    "SELECT CAST(value_in_use AS BIGINT) FROM sys.configurations WHERE name = 'user connections'"
                )
                max_conn_row = cursor.fetchone()
                max_connections = max_conn_row[0] if max_conn_row and max_conn_row[0] is not None else 0

                # Calculate uptime
                uptime = 0
                boot_time = None
                if row and row[5]:
                    from datetime import datetime, timezone
                    boot_time = row[5]
                    if boot_time.tzinfo is None:
                        boot_time = boot_time.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(timezone.utc)
                    uptime = int((now_utc - boot_time).total_seconds())

                # 2. 性能计数器（一次查询获取所有需要的计数器）
                cursor.execute(
                    "SELECT counter_name, cntr_value, cntr_type "
                    "FROM sys.dm_os_performance_counters "
                    "WHERE (counter_name = 'Batch Requests/sec' AND object_name LIKE '%SQL Statistics%') "
                    "   OR (counter_name = 'Transactions/sec' AND instance_name = '_Total' AND object_name LIKE '%Databases%') "
                    "   OR (counter_name = 'Buffer cache hit ratio' AND object_name LIKE '%Buffer Manager%') "
                    "   OR (counter_name = 'Buffer cache hit ratio base' AND object_name LIKE '%Buffer Manager%') "
                    "   OR (counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') "
                    "   OR (counter_name = 'Number of Deadlocks/sec' AND instance_name = '_Total' AND object_name LIKE '%Locks%') "
                    "   OR (counter_name = 'Lock Waits/sec' AND instance_name = '_Total' AND object_name LIKE '%Locks%') "
                    "   OR (counter_name = 'Page reads/sec' AND object_name LIKE '%Buffer Manager%') "
                    "   OR (counter_name = 'Page writes/sec' AND object_name LIKE '%Buffer Manager%') "
                    "   OR (counter_name = 'Network IO waits' AND object_name LIKE '%Wait Statistics%')"
                )
                counters = {}
                for r in cursor.fetchall():
                    counters[r[0].strip()] = int(r[1])

                batch_requests_total = counters.get('Batch Requests/sec', 0)
                transactions_total = counters.get('Transactions/sec', 0)
                cache_hit = counters.get('Buffer cache hit ratio', 0)
                cache_hit_base = counters.get('Buffer cache hit ratio base', 0)
                ple = counters.get('Page life expectancy', 0)
                deadlocks_total = counters.get('Number of Deadlocks/sec', 0)
                lock_waits_total = counters.get('Lock Waits/sec', 0)
                disk_reads_total = counters.get('Page reads/sec', 0)
                disk_writes_total = counters.get('Page writes/sec', 0)

                # 计算 buffer cache hit ratio（百分比）
                buffer_cache_hit_ratio = 0.0
                if cache_hit_base > 0:
                    buffer_cache_hit_ratio = round((cache_hit / cache_hit_base) * 100, 2)

                # 3. 数据库大小
                cursor.execute(
                    "SELECT SUM(size * 8 * 1024) FROM sys.database_files"
                )
                size_row = cursor.fetchone()
                db_size_bytes = size_row[0] if size_row and size_row[0] else 0

                # 4. 网络 IO（从 dm_exec_connections 获取累积字节数）
                cursor.execute(
                    "SELECT SUM(num_reads) as total_reads, "
                    "SUM(num_writes) as total_writes "
                    "FROM sys.dm_exec_connections"
                )
                net_row = cursor.fetchone()
                network_reads_total = net_row[0] if net_row and net_row[0] else 0
                network_writes_total = net_row[1] if net_row and net_row[1] else 0

                result = {
                    # 连接指标（兼容前端 fallback 链）
                    "connections_active": active_requests,
                    "user_sessions": visible_user_sessions,
                    "connections_total": visible_user_sessions,
                    "max_connections": max_connections,
                    "connections_idle": visible_idle_sessions,
                    "connections_waiting": blocked_requests,
                    "active_requests": active_requests,
                    # 吞吐量（累积值，由 normalizer 计算速率）
                    "batch_requests_total": batch_requests_total,
                    "transactions_total": transactions_total,
                    # 缓存与内存
                    "buffer_cache_hit_ratio": buffer_cache_hit_ratio,
                    "page_life_expectancy": ple,
                    # 锁与死锁（累积值）
                    "deadlocks_total": deadlocks_total,
                    "lock_waits_total": lock_waits_total,
                    # 磁盘 IO（累积值，由 normalizer 计算速率）
                    "disk_reads_total": disk_reads_total,
                    "disk_writes_total": disk_writes_total,
                    # 网络 IO（累积值）
                    "network_reads_total": network_reads_total,
                    "network_writes_total": network_writes_total,
                    # 数据库大小
                    "db_size_bytes": db_size_bytes,
                    # 运行时间
                    "uptime": uptime,
                    "boot_time": boot_time.isoformat() if boot_time else None,
                }

                return result
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _status)

    async def get_variables(self) -> Dict[str, Any]:
        import asyncio
        def _vars():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name, value_in_use FROM sys.configurations ORDER BY name")
                return {row[0]: str(row[1]) for row in cursor.fetchall()}
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _vars)

    async def get_process_list(self) -> List[Dict[str, Any]]:
        import asyncio
        def _procs():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT TOP 50 session_id, login_name, host_name, "
                    "program_name, status, cpu_time, memory_usage, "
                    "last_request_start_time "
                    "FROM sys.dm_exec_sessions WHERE is_user_process = 1 "
                    "ORDER BY cpu_time DESC"
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _procs)

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        import asyncio
        def _slow():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT TOP 20 qs.total_elapsed_time / qs.execution_count AS avg_elapsed, "
                    "qs.execution_count, qs.total_elapsed_time, "
                    "SUBSTRING(st.text, 1, 200) AS query_text "
                    "FROM sys.dm_exec_query_stats qs "
                    "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st "
                    "ORDER BY avg_elapsed DESC"
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _slow)

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        import asyncio
        def _exec():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                start = time.time()
                cursor.execute(sql)
                elapsed = round((time.time() - start) * 1000, 2)
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchmany(max_rows)
                    result = {
                        "columns": columns,
                        "rows": [list(r) for r in rows],
                        "row_count": len(rows),
                        "execution_time_ms": elapsed,
                        "truncated": len(rows) >= max_rows,
                    }
                    cursor.close()  # Close cursor to free connection
                    return result
                result = {
                    "columns": [], "rows": [], "row_count": cursor.rowcount,
                    "execution_time_ms": elapsed,
                    "message": f"Query OK, {cursor.rowcount} rows affected",
                }
                cursor.close()  # Close cursor to free connection
                return result
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _exec)

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        import asyncio
        def _explain():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SET SHOWPLAN_TEXT ON")
                cursor.execute(sql)
                rows = cursor.fetchall()
                cursor.execute("SET SHOWPLAN_TEXT OFF")
                return {
                    "plan": [row[0] for row in rows],
                }
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _explain)

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        import asyncio
        def _stats():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT TOP 50 t.name, p.rows, "
                    "SUM(a.total_pages) * 8 AS total_kb, "
                    "SUM(a.used_pages) * 8 AS used_kb "
                    "FROM sys.tables t "
                    "INNER JOIN sys.indexes i ON t.object_id = i.object_id "
                    "INNER JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id "
                    "INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id "
                    "GROUP BY t.name, p.rows ORDER BY total_kb DESC"
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _stats)

    async def get_replication_status(self) -> Dict[str, Any]:
        return {"status": "Use SQL Server Management Studio for replication details"}

    async def get_db_size(self) -> Dict[str, Any]:
        import asyncio
        def _size():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DB_NAME() as db_name, "
                    "SUM(size * 8 * 1024) as total_size "
                    "FROM sys.database_files"
                )
                row = cursor.fetchone()
                return {
                    "database": row[0] if row else self.database,
                    "total_size_bytes": row[1] if row else 0,
                }
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _size)

    async def get_schemas(self) -> List[str]:
        import asyncio
        def _schemas():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sys.schemas "
                    "WHERE name NOT IN ('guest', 'INFORMATION_SCHEMA', 'sys', 'db_owner', "
                    "'db_accessadmin', 'db_securityadmin', 'db_ddladmin', 'db_backupoperator', "
                    "'db_datareader', 'db_datawriter', 'db_denydatareader', 'db_denydatawriter') "
                    "ORDER BY name"
                )
                return [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _schemas)

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        import asyncio
        def _tables():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                target_schema = schema or "dbo"
                cursor.execute(
                    "SELECT t.name, s.name as schema_name, t.type_desc "
                    "FROM sys.tables t "
                    "INNER JOIN sys.schemas s ON t.schema_id = s.schema_id "
                    "WHERE s.name = ? "
                    "ORDER BY t.name",
                    (target_schema,)
                )
                columns = [col[0] for col in cursor.description]
                return [
                    {
                        "name": row[0],
                        "schema": row[1],
                        "type": row[2],
                    }
                    for row in cursor.fetchall()
                ]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _tables)

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        import asyncio
        def _columns():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                target_schema = schema or "dbo"
                cursor.execute(
                    "SELECT c.name, t.name as type_name, c.is_nullable, "
                    "c.max_length, c.precision, c.scale "
                    "FROM sys.columns c "
                    "INNER JOIN sys.types t ON c.user_type_id = t.user_type_id "
                    "INNER JOIN sys.tables tb ON c.object_id = tb.object_id "
                    "INNER JOIN sys.schemas s ON tb.schema_id = s.schema_id "
                    "WHERE s.name = ? AND tb.name = ? "
                    "ORDER BY c.column_id",
                    (target_schema, table)
                )
                return [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": bool(row[2]),
                        "max_length": row[3],
                        "precision": row[4],
                        "scale": row[5],
                    }
                    for row in cursor.fetchall()
                ]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _columns)
