import asyncio
import inspect
import time
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector
from backend.services.query_execution_state import QueryCancelledError


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
        connection = await asyncio.wait_for(
            oracledb.connect_async(
                user=self.username,
                password=self.password or "",
                dsn=dsn,
                mode=mode
            ),
            timeout=5
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
                "FROM v$session "
                "WHERE type = 'USER'"
            )
            session_stats = await cursor.fetchone()

            await cursor.execute(
                "SELECT value FROM v$parameter WHERE name = 'sessions'"
            )
            max_conn_row = await cursor.fetchone()
            max_connections = int(max_conn_row[0]) if max_conn_row and max_conn_row[0] is not None else 0

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
                "SELECT MAX((SYSDATE - start_date) * 86400) as seconds FROM v$transaction"
            )
            longest_tx_row = await cursor.fetchone()

            cursor.close()

            return {
                "connections_active": session_stats[1] if session_stats else 0,
                "connections_total": session_stats[0] if session_stats else 0,
                "max_connections": max_connections,
                "connections_idle": session_stats[2] if session_stats else 0,
                "connections_waiting": session_stats[3] if session_stats else 0,
                "lock_waiting": lock_row[0] if lock_row else 0,
                "longest_transaction_sec": int(longest_tx_row[0]) if longest_tx_row and longest_tx_row[0] else 0,
                "user_calls": sysstat.get('user calls', 0),
                "user_commits": sysstat.get('user commits', 0),
                "user_rollbacks": sysstat.get('user rollbacks', 0),
                "execute_count": sysstat.get('execute count', 0),
                "parse_count": sysstat.get('parse count (total)', 0),
                "physical_reads": sysstat.get('physical reads', 0),
                "physical_writes": sysstat.get('physical writes', 0),
                "redo_writes": sysstat.get('redo writes', 0),
                "network_bytes_sent": sysstat.get('bytes sent via SQL*Net to client', 0),
                "network_bytes_received": sysstat.get('bytes received via SQL*Net from client', 0),
                "cache_hit_rate": cache_hit_rate,
                "db_size_bytes": size_row[0] if size_row and size_row[0] else 0,
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
                "s.last_call_et, s.event, s.wait_class, "
                "SUBSTR(q.sql_text, 1, 500) as sql_text "
                "FROM v$session s "
                "LEFT JOIN v$sql q ON s.sql_id = q.sql_id AND s.sql_child_number = q.child_number "
                "WHERE s.type = 'USER' "
                "ORDER BY s.logon_time DESC"
            )
            rows = await cursor.fetchall()
            columns = [desc[0].lower() for desc in cursor.description]
            cursor.close()

            result = []
            for row in rows:
                session_dict = dict(zip(columns, row))
                # 将 last_call_et 映射为 duration_seconds
                if session_dict.get('last_call_et') is not None:
                    session_dict['duration_seconds'] = session_dict['last_call_et']
                # 将 event 映射为 wait_event（如果不是 Idle 类）
                if session_dict.get('wait_class') and session_dict['wait_class'] != 'Idle':
                    session_dict['wait_event'] = session_dict.get('event')
                result.append(session_dict)

            return result
        finally:
            await conn.close()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            # Oracle 11g兼容：使用ROWNUM代替FETCH FIRST N ROWS ONLY
            await cursor.execute(
                "SELECT sql_id, sql_text, executions, "
                "elapsed_time / 1000000 as elapsed_time_sec, "
                "cpu_time / 1000000 as cpu_time_sec, "
                "disk_reads, buffer_gets, rows_processed "
                "FROM ("
                "  SELECT sql_id, sql_text, executions, "
                "  elapsed_time, cpu_time, disk_reads, buffer_gets, rows_processed, "
                "  ROW_NUMBER() OVER (ORDER BY elapsed_time / executions DESC) as rn "
                "  FROM v$sql "
                "  WHERE executions > 0"
                ") WHERE rn <= 20"
            )
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]
        finally:
            await conn.close()

    async def _register_execution_session(self, conn, execution_state) -> None:
        if execution_state is None:
            return

        cursor = conn.cursor()
        try:
            await cursor.execute(
                "SELECT sid, serial# FROM v$session "
                "WHERE audsid = SYS_CONTEXT('USERENV', 'SESSIONID')"
            )
            row = await cursor.fetchone()
        finally:
            cursor.close()

        execution_state.session_id = f"{row[0]},{row[1]}" if row else None
        if execution_state.cancel_requested:
            raise QueryCancelledError("查询已取消")

    async def execute_query(
        self,
        sql: str,
        max_rows: int = 1000,
        execution_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        conn = await self._connect()
        cursor = None
        try:
            await self._register_execution_session(conn, execution_state)
            if execution_state is not None:
                execution_state.cancel_callback = conn.cancel
            cursor = conn.cursor()
            start = time.time()
            await cursor.execute(sql)
            elapsed = round((time.time() - start) * 1000, 2)

            has_result_set = bool(cursor.description)
            columns = [desc[0] for desc in cursor.description] if has_result_set else []

            if has_result_set:
                rows = await cursor.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                visible_rows = rows[:max_rows]
                result = {
                    "columns": columns,
                    "rows": [list(row) for row in visible_rows],
                    "row_count": len(visible_rows),
                    "execution_time_ms": elapsed,
                    "truncated": truncated,
                }
            else:
                await conn.commit()
                row_count = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                result = {
                    "columns": [],
                    "rows": [],
                    "row_count": row_count,
                    "execution_time_ms": elapsed,
                    "truncated": False,
                    "message": "Statement executed successfully",
                }

            return result
        except QueryCancelledError:
            raise
        except Exception as exc:
            if execution_state is not None and execution_state.cancel_requested:
                raise QueryCancelledError("查询已取消") from exc
            raise
        finally:
            if cursor is not None:
                cursor.close()
            await conn.close()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        """Get execution plan for SQL query (used by /api/query/explain)."""
        from backend.utils.sql_utils import extract_oracle_bind_variables

        conn = await self._connect()
        try:
            cursor = conn.cursor()

            # 提取绑定变量
            bind_vars = extract_oracle_bind_variables(sql)

            stmt_id = f"EXPLAIN_{int(time.time())}"

            # 为所有绑定变量提供 None 值
            if bind_vars:
                bind_params = {var: None for var in bind_vars}
                await cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {sql}", bind_params)
            else:
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
            # Oracle 11g兼容：使用ROWNUM代替FETCH FIRST N ROWS ONLY
            await cursor.execute(
                "SELECT owner, table_name, num_rows, blocks, "
                "avg_row_len, last_analyzed "
                "FROM ("
                "  SELECT owner, table_name, num_rows, blocks, "
                "  avg_row_len, last_analyzed "
                "  FROM dba_tables "
                "  WHERE owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP') "
                "  ORDER BY num_rows DESC NULLS LAST"
                ") WHERE ROWNUM <= 50"
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
                "SELECT database_role, protection_mode, protection_level FROM v$database"
            )
            row = await cursor.fetchone()

            if row and row[0] != 'PRIMARY':
                await cursor.execute(
                    "SELECT process, status, thread#, sequence# FROM v$managed_standby"
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

    async def terminate_session(self, session_id: int) -> Dict[str, Any]:
        """Terminate an Oracle session."""
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            # session_id 格式为 "sid,serial#"
            parts = str(session_id).split(',')
            if len(parts) != 2:
                raise ValueError("Oracle session_id 格式应为 'sid,serial#'")

            sid = int(parts[0])
            serial = int(parts[1])

            await cursor.execute(f"ALTER SYSTEM KILL SESSION '{sid},{serial}' IMMEDIATE")
            await conn.commit()
            cursor.close()

            return {
                "success": True,
                "session_id": session_id,
                "message": f"Oracle 会话 {session_id} 已终止",
            }
        finally:
            await conn.close()

    async def get_top_sql(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get TOP SQL statistics from v$sql."""
        conn = await self._connect()
        try:
            cursor = conn.cursor()
            await cursor.execute(f"""
                SELECT * FROM (
                    SELECT
                        sql_id,
                        sql_text,
                        sql_fulltext,
                        executions as exec_count,
                        ROUND(elapsed_time / 1000000, 6) as total_time_sec,
                        rows_processed as total_rows_scanned,
                        ROUND((elapsed_time - cpu_time) / 1000000, 6) as total_wait_time_sec,
                        ROUND(elapsed_time / GREATEST(executions, 1) / 1000000, 6) as avg_time_sec,
                        ROUND(rows_processed / GREATEST(executions, 1), 2) as avg_rows_scanned,
                        ROUND((elapsed_time - cpu_time) / GREATEST(executions, 1) / 1000000, 6) as avg_wait_time_sec,
                        last_active_time as last_exec_time
                    FROM v$sql
                    WHERE executions > 0
                    ORDER BY elapsed_time DESC
                ) WHERE ROWNUM <= {int(limit)}
            """)
            rows = await cursor.fetchall()
            columns = [desc[0].lower() for desc in cursor.description]
            cursor.close()

            results = []
            for row in rows:
                item = dict(zip(columns, row))
                full_sql = item.pop("sql_fulltext", None)
                if full_sql is not None:
                    # Oracle may return CLOB objects for sql_fulltext.
                    if hasattr(full_sql, "read"):
                        full_sql = full_sql.read()
                        if inspect.isawaitable(full_sql):
                            full_sql = await full_sql
                    item["sql_text"] = str(full_sql)
                elif item.get("sql_text") is not None:
                    item["sql_text"] = str(item["sql_text"])
                results.append(item)

            return results
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to get TOP SQL: {e}")
            return []
        finally:
            await conn.close()

    async def explain_sql(self, sql_text: str) -> Dict[str, Any]:
        """Get execution plan for SQL statement."""
        from backend.utils.sql_utils import extract_oracle_bind_variables

        conn = await self._connect()
        try:
            cursor = conn.cursor()

            # 提取绑定变量
            bind_vars = extract_oracle_bind_variables(sql_text)

            # 使用 EXPLAIN PLAN FOR 生成执行计划
            statement_id = f"EXPLAIN_{id(sql_text)}"
            explain_stmt = f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql_text}"

            # 为所有绑定变量提供 None 值
            if bind_vars:
                bind_params = {var: None for var in bind_vars}
                await cursor.execute(explain_stmt, bind_params)
            else:
                await cursor.execute(explain_stmt)

            # 查询执行计划
            await cursor.execute(f"""
                SELECT
                    id,
                    parent_id,
                    operation,
                    options,
                    object_name,
                    cost,
                    cardinality,
                    bytes,
                    cpu_cost,
                    io_cost
                FROM plan_table
                WHERE statement_id = '{statement_id}'
                ORDER BY id
            """)
            rows = await cursor.fetchall()
            columns = [desc[0].lower() for desc in cursor.description]

            # 清理执行计划表
            await cursor.execute(f"DELETE FROM plan_table WHERE statement_id = '{statement_id}'")
            await conn.commit()
            cursor.close()

            # 构建层级结构
            plan_rows = []
            operator_levels = {}  # id -> level

            # 第一遍：计算每个节点的层级
            rows_dict = {}
            for row in rows:
                row_id = row[0]
                parent_id = row[1]
                rows_dict[row_id] = (parent_id, row)

            # 递归计算层级
            def calc_level(node_id):
                if node_id in operator_levels:
                    return operator_levels[node_id]
                if node_id not in rows_dict:
                    return 0
                parent_id, _ = rows_dict[node_id]
                if parent_id is None:
                    operator_levels[node_id] = 0
                else:
                    operator_levels[node_id] = calc_level(parent_id) + 1
                return operator_levels[node_id]

            for row_id in rows_dict:
                calc_level(row_id)

            # 第二遍：构建带缩进的显示数据
            for row in rows:
                row_id = row[0]
                level = operator_levels.get(row_id, 0)
                indent = '  ' * level  # 每层缩进2个空格

                row_dict = dict(zip(columns, row))
                # 在 operation 前添加缩进
                operation = str(row_dict.get('operation', ''))
                options = str(row_dict.get('options', '')) if row_dict.get('options') else ''
                full_operation = f"{operation} {options}".strip() if options else operation
                row_dict['operation'] = indent + full_operation
                # 移除 options 列，因为已经合并到 operation 中
                row_dict.pop('options', None)
                plan_rows.append(row_dict)

            return {"format": "table", "plan": plan_rows}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to explain SQL: {e}")
            raise
        finally:
            await conn.close()
