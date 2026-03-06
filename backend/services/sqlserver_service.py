import time
from typing import Any, Dict, List
from backend.services.db_connector import DBConnector


class SQLServerConnector(DBConnector):
    """SQL Server connector using pyodbc."""

    def _get_conn_string(self):
        driver = "{ODBC Driver 18 for SQL Server}"
        s = (f"DRIVER={driver};SERVER={self.host},{self.port};"
             f"DATABASE={self.database or 'master'};"
             f"UID={self.username};PWD={self.password};"
             f"TrustServerCertificate=yes;Connection Timeout=10")
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
                cursor.execute(
                    "SELECT "
                    "(SELECT count(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1) as user_sessions, "
                    "(SELECT count(*) FROM sys.dm_exec_requests) as active_requests, "
                    "(SELECT cntr_value FROM sys.dm_os_performance_counters "
                    " WHERE counter_name = 'Batch Requests/sec') as batch_requests, "
                    "(SELECT cntr_value FROM sys.dm_os_performance_counters "
                    " WHERE counter_name = 'Buffer cache hit ratio') as buffer_cache_hit, "
                    "(SELECT cntr_value FROM sys.dm_os_performance_counters "
                    " WHERE counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') as ple"
                )
                row = cursor.fetchone()
                return {
                    "user_sessions": row[0] if row else 0,
                    "active_requests": row[1] if row else 0,
                    "batch_requests_sec": row[2] if row else 0,
                    "buffer_cache_hit_ratio": row[3] if row else 0,
                    "page_life_expectancy": row[4] if row else 0,
                }
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
