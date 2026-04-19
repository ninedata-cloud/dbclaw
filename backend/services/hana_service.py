import asyncio
import re
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class HANAConnector(DBConnector):
    """SAP HANA database connector using hdbcli."""

    def __init__(self, host: str, port: int, username: str = None,
                 password: str = None, database: str = None, **kwargs):
        super().__init__(host, port, username, password, database)
        self.encrypt = kwargs.get('encrypt', False)
        self.sslValidateCertificate = kwargs.get('sslValidateCertificate', False)

    @staticmethod
    def _validate_identifier(identifier: str) -> str:
        """验证并清理 SQL 标识符，防止 SQL 注入"""
        if not identifier:
            raise ValueError("Identifier cannot be empty")
        # 只允许字母、数字、下划线和美元符号（HANA 支持）
        if not re.match(r'^[A-Za-z0-9_$]+$', identifier):
            raise ValueError(f"Invalid identifier: {identifier}")
        return identifier

    async def _connect(self):
        """Create HANA connection in thread pool."""
        from hdbcli import dbapi

        def _sync_connect():
            return dbapi.connect(
                address=self.host,
                port=self.port,
                user=self.username,
                password=self.password or "",
                databaseName=self.database or "",
                encrypt=self.encrypt,
                sslValidateCertificate=self.sslValidateCertificate,
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_connect)

    async def _execute_query(self, conn, query: str, fetch_one: bool = False):
        """Execute query in thread pool."""
        def _sync_execute():
            cursor = conn.cursor()
            try:
                cursor.execute(query)
                if fetch_one:
                    return cursor.fetchone()
                return cursor.fetchall()
            finally:
                cursor.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_execute)

    async def test_connection(self) -> str:
        conn = await self._connect()
        try:
            row = await self._execute_query(conn, "SELECT VERSION FROM SYS.M_DATABASE", fetch_one=True)
            return row[0] if row else "unknown"
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            # 连接数统计
            conn_stats = await self._execute_query(
                conn,
                """SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN CONNECTION_STATUS = 'RUNNING' THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN CONNECTION_STATUS = 'IDLE' THEN 1 ELSE 0 END) as idle
                FROM SYS.M_CONNECTIONS
                WHERE CONNECTION_TYPE NOT LIKE 'History%'"""
            )

            # 事务统计 - 使用 M_TRANSACTIONS 视图
            tx_stats = await self._execute_query(
                conn,
                """SELECT
                    COUNT(*) as tx_count
                FROM SYS.M_TRANSACTIONS"""
            )

            # 内存使用
            mem_stats = await self._execute_query(
                conn,
                """SELECT
                    SUM(TOTAL_MEMORY_USED_SIZE) as used_memory,
                    SUM(PHYSICAL_MEMORY_SIZE) as total_memory
                FROM SYS.M_SERVICE_MEMORY"""
            )

            # 数据库大小
            db_size = await self._execute_query(
                conn,
                "SELECT SUM(DISK_SIZE) as db_size FROM SYS.M_TABLE_PERSISTENCE_STATISTICS"
            )

            # 运行时间
            uptime_row = await self._execute_query(
                conn,
                "SELECT SECONDS_BETWEEN(START_TIME, CURRENT_TIMESTAMP) as uptime FROM SYS.M_DATABASE",
                fetch_one=True
            )

            # 锁等待
            lock_waits = await self._execute_query(
                conn,
                "SELECT COUNT(*) as cnt FROM SYS.M_BLOCKED_TRANSACTIONS"
            )

            conn_total = conn_stats[0][0] if conn_stats and conn_stats[0] else 0
            conn_active = conn_stats[0][1] if conn_stats and conn_stats[0] else 0
            conn_idle = conn_stats[0][2] if conn_stats and conn_stats[0] else 0

            tx_count = tx_stats[0][0] if tx_stats and tx_stats[0] and tx_stats[0][0] else 0

            used_memory = mem_stats[0][0] if mem_stats and mem_stats[0] and mem_stats[0][0] else 0
            total_memory = mem_stats[0][1] if mem_stats and mem_stats[0] and mem_stats[0][1] else 0

            db_size_bytes = db_size[0][0] if db_size and db_size[0] and db_size[0][0] else 0
            uptime = uptime_row[0] if uptime_row and uptime_row[0] else 0
            lock_waiting = lock_waits[0][0] if lock_waits and lock_waits[0] else 0

            return {
                "connections_active": conn_active,
                "connections_total": conn_total,
                "connections_idle": conn_idle,
                "transactions_active": tx_count,
                "lock_waiting": lock_waiting,
                "db_size_bytes": db_size_bytes,
                "used_memory_bytes": used_memory,
                "total_memory_bytes": total_memory,
                "uptime": uptime,
            }
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_variables(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                "SELECT KEY, VALUE FROM SYS.M_INIFILE_CONTENTS WHERE LAYER_NAME = 'DEFAULT'"
            )
            return {r[0]: r[1] for r in rows} if rows else {}
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_process_list(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT
                    CONNECTION_ID, USER_NAME, CLIENT_IP,
                    CONNECTION_STATUS, CURRENT_STATEMENT_ID,
                    LAST_ACTION, CURRENT_SCHEMA_NAME,
                    IDLE_TIME
                FROM SYS.M_CONNECTIONS
                WHERE CONNECTION_TYPE NOT LIKE 'History%'
                ORDER BY LAST_ACTION DESC"""
            )

            result = []
            for r in rows:
                # 将 HANA 字段映射为标准字段名
                result.append({
                    "id": r[0],  # CONNECTION_ID -> id (用于 session_id)
                    "user": r[1],  # USER_NAME -> user
                    "host": r[2],  # CLIENT_IP -> host (用于 client)
                    "db": r[6],  # CURRENT_SCHEMA_NAME -> db (用于 database)
                    "command": r[3],  # CONNECTION_STATUS -> command (用于 status)
                    "time": r[7] // 1000 if r[7] else 0,  # IDLE_TIME (微秒) -> time (秒，用于 duration_seconds)
                    "state": r[5],  # LAST_ACTION -> state (用于 wait_event)
                    "info": None,  # 当前 SQL 需要从其他视图查询
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT TOP 100
                    STATEMENT_STRING,
                    DURATION_MICROSEC / 1000000.0 as duration_sec,
                    START_TIME, USER_NAME, CONNECTION_ID
                FROM SYS.M_EXPENSIVE_STATEMENTS
                ORDER BY DURATION_MICROSEC DESC"""
            )

            result = []
            for r in rows:
                result.append({
                    "query": r[0],
                    "duration": r[1],
                    "start_time": r[2],
                    "user": r[3],
                    "connection_id": r[4],
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            def _sync_execute():
                cursor = conn.cursor()
                try:
                    cursor.execute(sql)
                    rows = cursor.fetchmany(max_rows)
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    return columns, rows
                finally:
                    cursor.close()

            loop = asyncio.get_event_loop()
            columns, rows = await loop.run_in_executor(None, _sync_execute)

            return {
                "columns": columns,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
            }
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                f"EXPLAIN PLAN FOR {sql}"
            )

            return {
                "plan": [{"line": str(r[0])} for r in rows] if rows else [],
            }
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT
                    SCHEMA_NAME, TABLE_NAME, RECORD_COUNT,
                    DISK_SIZE, MEMORY_SIZE_IN_TOTAL
                FROM SYS.M_TABLES
                WHERE SCHEMA_NAME NOT IN ('SYS', '_SYS_STATISTICS', '_SYS_REPO')
                ORDER BY MEMORY_SIZE_IN_TOTAL DESC"""
            )

            result = []
            for r in rows:
                result.append({
                    "schema": r[0],
                    "table": r[1],
                    "rows": r[2],
                    "disk_size": r[3],
                    "memory_size": r[4],
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_replication_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT
                    REPLICATION_MODE, REPLICATION_STATUS,
                    SECONDARY_HOST, SECONDARY_PORT
                FROM SYS.M_SERVICE_REPLICATION
                WHERE REPLICATION_STATUS IS NOT NULL"""
            )

            if not rows or not rows[0]:
                return {"enabled": False}

            r = rows[0]
            return {
                "enabled": True,
                "mode": r[0],
                "status": r[1],
                "secondary_host": r[2],
                "secondary_port": r[3],
            }
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_db_size(self) -> Dict[str, Any]:
        """获取数据库大小信息"""
        conn = await self._connect()
        try:
            # 获取表数据大小
            data_size_row = await self._execute_query(
                conn,
                "SELECT SUM(USED_SIZE) as data_size FROM SYS.M_TABLE_PERSISTENCE_STATISTICS",
                fetch_one=True
            )

            # 获取日志大小
            log_size_row = await self._execute_query(
                conn,
                "SELECT SUM(TOTAL_SIZE) as log_size FROM SYS.M_LOG_SEGMENTS",
                fetch_one=True
            )

            data_size = data_size_row[0] if data_size_row and data_size_row[0] else 0
            log_size = log_size_row[0] if log_size_row and log_size_row[0] else 0

            return {
                "database": self.database or "SYSTEMDB",
                "total_size_bytes": data_size + log_size,
                "data_size_bytes": data_size,
                "log_size_bytes": log_size,
            }
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_index_stats(self) -> List[Dict[str, Any]]:
        """获取索引统计信息"""
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT
                    SCHEMA_NAME, TABLE_NAME, INDEX_NAME,
                    INDEX_TYPE, MEMORY_SIZE_IN_TOTAL
                FROM SYS.M_INDEXES
                WHERE SCHEMA_NAME NOT LIKE '_SYS%'
                ORDER BY MEMORY_SIZE_IN_TOTAL DESC
                LIMIT 100"""
            )

            result = []
            for r in rows:
                result.append({
                    "schema": r[0],
                    "table": r[1],
                    "index": r[2],
                    "type": r[3],
                    "size_bytes": r[4],
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_table_fragmentation(self) -> List[Dict[str, Any]]:
        """获取表碎片化信息"""
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT
                    SCHEMA_NAME, TABLE_NAME, RECORD_COUNT,
                    DISK_SIZE, MEMORY_SIZE_IN_TOTAL,
                    CASE
                        WHEN DISK_SIZE > 0 AND MEMORY_SIZE_IN_TOTAL > 0
                        THEN ROUND((DISK_SIZE - MEMORY_SIZE_IN_TOTAL) * 100.0 / DISK_SIZE, 2)
                        ELSE 0
                    END as fragmentation_pct
                FROM SYS.M_TABLES
                WHERE SCHEMA_NAME NOT LIKE '_SYS%'
                  AND DISK_SIZE > 0
                ORDER BY fragmentation_pct DESC
                LIMIT 100"""
            )

            result = []
            for r in rows:
                result.append({
                    "schema": r[0],
                    "table": r[1],
                    "rows": r[2],
                    "disk_size": r[3],
                    "memory_size": r[4],
                    "fragmentation_pct": r[5],
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_schemas(self) -> List[str]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                "SELECT SCHEMA_NAME FROM SYS.SCHEMAS WHERE SCHEMA_NAME NOT LIKE '_SYS%' ORDER BY SCHEMA_NAME"
            )
            return [r[0] for r in rows] if rows else []
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            if schema:
                # 验证 schema 名称防止 SQL 注入
                safe_schema = self._validate_identifier(schema)
                query = f"""SELECT TABLE_NAME, TABLE_TYPE, RECORD_COUNT
                           FROM SYS.TABLES
                           WHERE SCHEMA_NAME = '{safe_schema}'
                           ORDER BY TABLE_NAME"""
            else:
                query = """SELECT SCHEMA_NAME, TABLE_NAME, TABLE_TYPE, RECORD_COUNT
                          FROM SYS.TABLES
                          WHERE SCHEMA_NAME NOT LIKE '_SYS%'
                          ORDER BY SCHEMA_NAME, TABLE_NAME"""

            rows = await self._execute_query(conn, query)

            result = []
            if schema:
                for r in rows:
                    result.append({
                        "table": r[0],
                        "type": r[1],
                        "rows": r[2],
                    })
            else:
                for r in rows:
                    result.append({
                        "schema": r[0],
                        "table": r[1],
                        "type": r[2],
                        "rows": r[3],
                    })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            # 验证标识符防止 SQL 注入
            safe_table = self._validate_identifier(table)

            if schema:
                safe_schema = self._validate_identifier(schema)
                query = f"""SELECT COLUMN_NAME, DATA_TYPE_NAME, LENGTH,
                           IS_NULLABLE, DEFAULT_VALUE
                           FROM SYS.TABLE_COLUMNS
                           WHERE SCHEMA_NAME = '{safe_schema}' AND TABLE_NAME = '{safe_table}'
                           ORDER BY POSITION"""
            else:
                query = f"""SELECT COLUMN_NAME, DATA_TYPE_NAME, LENGTH,
                           IS_NULLABLE, DEFAULT_VALUE
                           FROM SYS.TABLE_COLUMNS
                           WHERE TABLE_NAME = '{safe_table}'
                           ORDER BY POSITION"""

            rows = await self._execute_query(conn, query)

            result = []
            for r in rows:
                result.append({
                    "column": r[0],
                    "type": r[1],
                    "length": r[2],
                    "nullable": r[3] == 'TRUE',
                    "default": r[4],
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def get_lock_waits(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await self._execute_query(
                conn,
                """SELECT
                    WAITING_CONNECTION_ID, WAITING_STATEMENT_ID,
                    BLOCKING_CONNECTION_ID, BLOCKING_STATEMENT_ID,
                    LOCK_TYPE, LOCK_MODE
                FROM SYS.M_BLOCKED_TRANSACTIONS"""
            )

            result = []
            for r in rows:
                result.append({
                    "waiting_connection": r[0],
                    "waiting_statement": r[1],
                    "blocking_connection": r[2],
                    "blocking_statement": r[3],
                    "lock_type": r[4],
                    "lock_mode": r[5],
                })
            return result
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def terminate_session(self, session_id: int) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            await self._execute_query(
                conn,
                f"ALTER SYSTEM DISCONNECT SESSION '{session_id}'"
            )
            return {"success": True, "message": f"Session {session_id} terminated"}
        except Exception as e:
            return {"success": False, "message": str(e)}
        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def close(self):
        """Clean up connections."""
        pass
