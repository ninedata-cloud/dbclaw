import os
import time
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


_PROCESS_LIST_SQL = """
SELECT TOP 100
    s.session_id,
    s.login_name,
    s.host_name,
    s.program_name,
    s.status,
    s.cpu_time,
    s.memory_usage,
    s.last_request_start_time,
    DB_NAME(COALESCE(r.database_id, sp.dbid, sql_text.dbid)) AS database_name,
    c.client_net_address,
    r.wait_type,
    SUBSTRING(
        sql_text.text,
        CASE
            WHEN r.statement_start_offset IS NULL OR r.statement_start_offset < 0 THEN 1
            ELSE (r.statement_start_offset / 2) + 1
        END,
        CASE
            WHEN r.statement_end_offset IS NULL OR r.statement_end_offset < 0 THEN 4000
            ELSE ((r.statement_end_offset - r.statement_start_offset) / 2) + 1
        END
    ) AS current_sql
FROM sys.dm_exec_sessions s
LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id
LEFT JOIN sys.dm_exec_connections c ON s.session_id = c.session_id
LEFT JOIN sys.sysprocesses sp ON s.session_id = sp.spid
OUTER APPLY sys.dm_exec_sql_text(COALESCE(r.sql_handle, c.most_recent_sql_handle)) sql_text
WHERE s.is_user_process = 1
ORDER BY COALESCE(r.cpu_time, s.cpu_time) DESC, s.last_request_start_time DESC
"""


class SQLServerConnector(DBConnector):
    """SQL Server connector using pyodbc."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str = None,
        password: str = None,
        database: str = None,
        encrypt: Optional[Any] = None,
        trust_server_certificate: Optional[Any] = None,
        odbc_driver: Optional[str] = None,
        connection_timeout: Optional[Any] = None,
        **_: Any,
    ):
        super().__init__(host, port, username=username, password=password, database=database)
        self.encrypt = self._normalize_encrypt_setting(encrypt)
        self.trust_server_certificate = self._normalize_bool(
            trust_server_certificate,
            default=True,
        )
        self.odbc_driver = (str(odbc_driver).strip() if odbc_driver is not None else "") or None
        self.connection_timeout = self._normalize_timeout(connection_timeout, default=5)

    @staticmethod
    def _normalize_bool(value: Optional[Any], *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _normalize_encrypt_setting(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return "no"
        if isinstance(value, bool):
            return "yes" if value else "no"
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "mandatory", "strict"}:
            return "yes"
        if normalized in {"0", "false", "no", "off", "optional"}:
            return "no"
        return None

    @staticmethod
    def _normalize_timeout(value: Optional[Any], *, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    def _resolve_driver_name(self, pyodbc_module=None) -> str:
        if self.odbc_driver:
            return self.odbc_driver.strip().strip("{}")
        configured_driver = os.getenv("SQLSERVER_ODBC_DRIVER", "").strip().strip("{}")
        if configured_driver:
            return configured_driver

        pyodbc_module = pyodbc_module or __import__("pyodbc")
        available_drivers = set(pyodbc_module.drivers())
        for driver_name in (
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 18 for SQL Server",
            "FreeTDS",
        ):
            if driver_name in available_drivers:
                return driver_name

        return "ODBC Driver 17 for SQL Server"

    def _get_conn_string(self, driver_name: Optional[str] = None):
        driver_name = (driver_name or self._resolve_driver_name()).strip("{}")
        driver = f"{{{driver_name}}}"
        parts = [
            f"DRIVER={driver}",
            f"SERVER={self.host},{self.port}",
            f"DATABASE={self.database or 'master'}",
            f"UID={self.username}",
            f"PWD={self.password}",
            f"TrustServerCertificate={'yes' if self.trust_server_certificate else 'no'}",
            f"Connection Timeout={self.connection_timeout}",
        ]
        if self.encrypt is not None:
            parts.append(f"Encrypt={self.encrypt}")
        return ";".join(parts)

    @staticmethod
    def _build_ssl_protocol_error_message(message: str, driver_name: str) -> str:
        return (
            "SQL Server SSL/TLS 握手失败：服务端很可能只支持较老 TLS 协议，而当前客户端驱动无法协商。"
            f"当前驱动: {driver_name}。"
            "如果是 SQL Server 2012，可先在数据源高级参数中设置 Encrypt=no；"
            "若仍失败，请改用 ODBC Driver 17，或在服务端启用 TLS 1.2。"
            f"原始错误: {message}"
        )

    def _connect(self):
        import pyodbc
        driver_name = self._resolve_driver_name(pyodbc)
        try:
            conn = pyodbc.connect(self._get_conn_string(driver_name), autocommit=True)

            # Handle sql_variant columns such as sys.configurations.value consistently.
            def handle_sql_variant(value):
                return str(value) if value is not None else None

            conn.add_output_converter(-16, handle_sql_variant)
            return conn
        except pyodbc.Error as exc:
            available_drivers = ", ".join(pyodbc.drivers()) or "none"
            message = str(exc)
            lowered = message.lower()
            if "driver manager" in lowered or "data source name not found" in lowered:
                raise RuntimeError(
                    f"SQL Server ODBC 驱动不可用，当前尝试: {driver_name}；已安装驱动: {available_drivers}。"
                    "请在镜像中安装 msodbcsql17，或通过环境变量 SQLSERVER_ODBC_DRIVER 指定已安装驱动。"
                ) from exc
            if "ssl provider" in lowered and "unsupported protocol" in lowered:
                raise RuntimeError(self._build_ssl_protocol_error_message(message, driver_name)) from exc
            raise

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
                    "(SELECT sqlserver_start_time FROM sys.dm_os_sys_info) as start_time "
                )
                row = cursor.fetchone()

                total_sessions = row[0] if row else 0
                user_sessions = row[1] if row else 0
                active_requests = row[2] if row else 0
                idle_sessions = row[3] if row else 0
                blocked_requests = row[4] if row else 0
                visible_user_sessions = user_sessions
                visible_idle_sessions = idle_sessions

                cursor.execute(
                    "SELECT CAST(value_in_use AS BIGINT) FROM sys.configurations WHERE name = 'user connections'"
                )
                max_conn_row = cursor.fetchone()
                configured_connections = max_conn_row[0] if max_conn_row and max_conn_row[0] is not None else 0

                # SQL Server 中 user connections = 0 表示使用实例允许的最大连接数，
                # 不是“未知”或“无配置”，此时回退到 @@MAX_CONNECTIONS 以便前端展示。
                cursor.execute("SELECT CAST(@@MAX_CONNECTIONS AS BIGINT)")
                server_max_row = cursor.fetchone()
                server_max_connections = server_max_row[0] if server_max_row and server_max_row[0] is not None else 0
                max_connections = (
                    configured_connections
                    if configured_connections and configured_connections > 0
                    else server_max_connections
                )

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
                cursor.execute(
                    "SELECT name, "
                    "COALESCE(CONVERT(NVARCHAR(256), value_in_use), CONVERT(NVARCHAR(256), value), '') AS value_text "
                    "FROM sys.configurations ORDER BY name"
                )
                return {row[0]: row[1] for row in cursor.fetchall()}
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _vars)

    async def get_process_list(self) -> List[Dict[str, Any]]:
        import asyncio
        def _procs():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(_PROCESS_LIST_SQL)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _procs)

    async def terminate_session(self, session_id: int) -> Dict[str, Any]:
        import asyncio
        def _terminate():
            conn = self._connect()
            try:
                target_session_id = int(session_id)
                cursor = conn.cursor()
                cursor.execute(f"KILL {target_session_id}")
                return {
                    "success": True,
                    "session_id": target_session_id,
                    "message": f"SQL Server 会话 {target_session_id} 已终止",
                }
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _terminate)

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
                    rows = cursor.fetchmany(max_rows + 1)
                    truncated = len(rows) > max_rows
                    visible_rows = rows[:max_rows]
                    result = {
                        "columns": columns,
                        "rows": [list(r) for r in visible_rows],
                        "row_count": len(visible_rows),
                        "execution_time_ms": elapsed,
                        "truncated": truncated,
                    }
                    cursor.close()  # Close cursor to free connection
                    return result
                row_count = cursor.rowcount if cursor.rowcount >= 0 else 0
                result = {
                    "columns": [], "rows": [], "row_count": row_count,
                    "execution_time_ms": elapsed,
                    "truncated": False,
                    "message": f"Query OK, {row_count} rows affected",
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

    async def get_top_sql(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get TOP SQL statistics from sys.dm_exec_query_stats."""
        import asyncio
        def _top_sql():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(f"""
                    WITH QueryStats AS (
                        SELECT
                            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                                ((CASE qs.statement_end_offset
                                    WHEN -1 THEN DATALENGTH(qt.text)
                                    ELSE qs.statement_end_offset
                                END - qs.statement_start_offset)/2) + 1) AS sql_text,
                            qs.execution_count,
                            qs.total_elapsed_time,
                            qs.total_worker_time,
                            qs.total_rows,
                            qs.last_execution_time
                        FROM sys.dm_exec_query_stats qs
                        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
                        WHERE qs.execution_count > 0
                    )
                    SELECT TOP {int(limit)}
                        sql_text,
                        CONVERT(VARCHAR(64), HASHBYTES('MD5', sql_text), 2) AS sql_id,
                        execution_count AS exec_count,
                        ROUND(total_elapsed_time / 1000000.0, 6) AS total_time_sec,
                        total_rows AS total_rows_scanned,
                        ROUND((total_elapsed_time - total_worker_time) / 1000000.0, 6) AS total_wait_time_sec,
                        ROUND(total_elapsed_time / CAST(execution_count AS FLOAT) / 1000000.0, 6) AS avg_time_sec,
                        ROUND(total_rows / CAST(execution_count AS FLOAT), 2) AS avg_rows_scanned,
                        ROUND((total_elapsed_time - total_worker_time) / CAST(execution_count AS FLOAT) / 1000000.0, 6) AS avg_wait_time_sec,
                        last_execution_time
                    FROM QueryStats
                    ORDER BY total_elapsed_time DESC
                """)
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to get TOP SQL: {e}")
                return []
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _top_sql)

    async def explain_sql(self, sql_text: str) -> Dict[str, Any]:
        """Get execution plan for SQL statement."""
        import asyncio
        def _explain():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                # 启用 SHOWPLAN_ALL
                cursor.execute("SET SHOWPLAN_ALL ON")
                cursor.execute(sql_text)
                columns = [desc[0] for desc in cursor.description]
                plan_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                cursor.execute("SET SHOWPLAN_ALL OFF")
                return {"format": "table", "plan": plan_rows}
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to explain SQL: {e}")
                raise
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _explain)
