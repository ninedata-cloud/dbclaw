import time
import asyncio
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class DMConnector(DBConnector):
    """DM (Dameng) database connector using dmPython (synchronous, Oracle-like)."""

    def _connect(self):
        try:
            import dmPython
            import socket
            conn_str = f"{self.username}/{self.password}@{self.host}:{self.port}"
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(5)
            try:
                return dmPython.connect(conn_str)
            finally:
                socket.setdefaulttimeout(old_timeout)
        except ImportError:
            raise ImportError("dmPython library not installed. Install with: pip install dmPython")

    async def test_connection(self) -> str:
        def _test():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM V$VERSION WHERE ROWNUM = 1")
                row = cursor.fetchone()
                return row[0] if row else "unknown"
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _test)

    async def get_status(self) -> Dict[str, Any]:
        def _status():
            conn = self._connect()
            try:
                cursor = conn.cursor()

                # Get session count
                cursor.execute("SELECT COUNT(*) FROM V$SESSION")
                session_count = cursor.fetchone()[0]

                # Get active sessions
                cursor.execute("SELECT COUNT(*) FROM V$SESSION WHERE STATUS = 'ACTIVE'")
                active_sessions = cursor.fetchone()[0]

                # Get configured max sessions
                cursor.execute("SELECT VALUE FROM V$PARAMETER WHERE NAME = 'SESSIONS' AND ROWNUM = 1")
                max_sessions_row = cursor.fetchone()
                max_connections = int(max_sessions_row[0]) if max_sessions_row and max_sessions_row[0] is not None else 0

                # Get system statistics
                cursor.execute(
                    "SELECT NAME, VALUE FROM V$SYSSTAT "
                    "WHERE NAME IN ('user commits', 'user rollbacks', 'physical reads', 'db block gets') "
                    "AND ROWNUM <= 10"
                )
                stats = {row[0]: row[1] for row in cursor.fetchall()}

                # Get database startup time
                cursor.execute("SELECT STARTUP_TIME FROM V$INSTANCE WHERE ROWNUM = 1")
                startup_row = cursor.fetchone()

                # Calculate uptime
                uptime = 0
                boot_time = None
                if startup_row and startup_row[0]:
                    from datetime import datetime, timezone
                    boot_time = startup_row[0]
                    if boot_time.tzinfo is None:
                        boot_time = boot_time.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    uptime = int((now - boot_time).total_seconds())

                return {
                    "session_count": session_count,
                    "active_sessions": active_sessions,
                    "connections_total": session_count,
                    "connections_active": active_sessions,
                    "max_connections": max_connections,
                    "user_commits": int(stats.get("user commits", 0)),
                    "user_rollbacks": int(stats.get("user rollbacks", 0)),
                    "physical_reads": int(stats.get("physical reads", 0)),
                    "db_block_gets": int(stats.get("db block gets", 0)),
                    "uptime": uptime,
                    "boot_time": boot_time.isoformat() if boot_time else None,
                }
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _status)

    async def get_variables(self) -> Dict[str, Any]:
        def _vars():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT NAME, VALUE FROM V$PARAMETER ORDER BY NAME")
                return {row[0]: str(row[1]) for row in cursor.fetchall()}
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _vars)

    async def get_process_list(self) -> List[Dict[str, Any]]:
        def _procs():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT SID, SERIAL#, USERNAME, STATUS, OSUSER, MACHINE, PROGRAM, SQL_ID "
                    "FROM V$SESSION WHERE USERNAME IS NOT NULL AND ROWNUM <= 50 "
                    "ORDER BY LOGON_TIME DESC"
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _procs)

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        def _slow():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                try:
                    # Try to get from audit trail
                    cursor.execute(
                        "SELECT TIMESTAMP, USERNAME, SQL_TEXT, ELAPSED_TIME "
                        "FROM DBA_AUDIT_TRAIL "
                        "WHERE ELAPSED_TIME > 1000 AND ROWNUM <= 20 "
                        "ORDER BY TIMESTAMP DESC"
                    )
                    columns = [col[0] for col in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                except Exception:
                    return [{"message": "Audit trail not accessible"}]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _slow)

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        def _exec():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                start = time.time()
                cursor.execute(sql)
                elapsed = round((time.time() - start) * 1000, 2)

                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    fetched_rows = cursor.fetchmany(max_rows + 1)
                    truncated = len(fetched_rows) > max_rows
                    visible_rows = fetched_rows[:max_rows]
                    return {
                        "columns": columns,
                        "rows": [list(row) for row in visible_rows],
                        "row_count": len(visible_rows),
                        "execution_time_ms": elapsed,
                        "truncated": truncated,
                    }
                else:
                    row_count = cursor.rowcount if cursor.rowcount >= 0 else 0
                    conn.commit()
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
        return await asyncio.get_event_loop().run_in_executor(None, _exec)

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        def _explain():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                # DM uses Oracle-style EXPLAIN PLAN
                cursor.execute(f"EXPLAIN PLAN FOR {sql}")
                cursor.execute(
                    "SELECT PLAN_TABLE_OUTPUT FROM TABLE(DBMS_XPLAN.DISPLAY())"
                )
                rows = cursor.fetchall()
                return {
                    "plan": [row[0] for row in rows]
                }
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _explain)

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        def _stats():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT TABLE_NAME, NUM_ROWS, BLOCKS, AVG_ROW_LEN, LAST_ANALYZED "
                    "FROM DBA_TABLES WHERE OWNER = USER AND ROWNUM <= 50 "
                    "ORDER BY NUM_ROWS DESC"
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _stats)

    async def get_replication_status(self) -> Dict[str, Any]:
        def _repl():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                try:
                    # Check for Data Guard or replication
                    cursor.execute(
                        "SELECT DATABASE_ROLE, OPEN_MODE, PROTECTION_MODE "
                        "FROM V$DATABASE"
                    )
                    row = cursor.fetchone()
                    if row:
                        return {
                            "database_role": row[0],
                            "open_mode": row[1],
                            "protection_mode": row[2],
                        }
                except Exception:
                    pass
                return {"status": "not configured"}
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _repl)

    async def get_db_size(self) -> Dict[str, Any]:
        def _size():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT SUM(BYTES) as total_size "
                    "FROM DBA_DATA_FILES"
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "total_size_bytes": int(row[0] or 0),
                    }
                return {}
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _size)

    async def get_schemas(self) -> List[str]:
        def _schemas():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT USERNAME FROM DBA_USERS "
                    "WHERE USERNAME NOT IN ('SYS', 'SYSTEM', 'SYSDBA', 'SYSSSO', 'SYSAUDITOR') "
                    "ORDER BY USERNAME"
                )
                return [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _schemas)

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        def _tables():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                target_schema = schema or self.username.upper()
                cursor.execute(
                    "SELECT TABLE_NAME, TABLESPACE_NAME, NUM_ROWS "
                    "FROM DBA_TABLES WHERE OWNER = :1 "
                    "ORDER BY TABLE_NAME",
                    (target_schema,)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "name": row[0],
                        "schema": target_schema,
                        "tablespace": row[1],
                        "num_rows": row[2],
                    }
                    for row in rows
                ]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _tables)

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        def _columns():
            conn = self._connect()
            try:
                cursor = conn.cursor()
                target_schema = schema or self.username.upper()
                cursor.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT, DATA_LENGTH "
                    "FROM DBA_TAB_COLUMNS "
                    "WHERE OWNER = :1 AND TABLE_NAME = :2 "
                    "ORDER BY COLUMN_ID",
                    (target_schema, table.upper())
                )
                rows = cursor.fetchall()
                return [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "Y",
                        "default": row[3],
                        "length": row[4],
                    }
                    for row in rows
                ]
            finally:
                conn.close()
        return await asyncio.get_event_loop().run_in_executor(None, _columns)
