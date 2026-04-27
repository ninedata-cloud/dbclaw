import asyncio
import logging
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector
from backend.services.query_execution_state import QueryCancelledError

logger = logging.getLogger(__name__)


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
        return await aiomysql.connect(**self._get_conn_params(), connect_timeout=5)

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

                await cur.execute(
                    "SELECT "
                    "COUNT(*) as total, "
                    "SUM(CASE WHEN COMMAND != 'Sleep' THEN 1 ELSE 0 END) as active "
                    "FROM information_schema.PROCESSLIST "
                )
                process_stats = await cur.fetchone()
                process_count = process_stats[0] if process_stats else 0

                await cur.execute("SHOW GLOBAL VARIABLES LIKE 'max_connections'")
                max_conn_row = await cur.fetchone()
                max_connections = int(max_conn_row[1]) if max_conn_row and max_conn_row[1] is not None else 0

                uptime = max(int(status.get("Uptime", 1)), 1)

                # 优先使用 SHOW GLOBAL STATUS 的值（更准确且不受权限限制）
                # 安全转换：处理字符串、None、空值等情况
                def safe_int(value, default=0):
                    if value is None or value == '':
                        return default
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        return default

                global_threads_running = safe_int(status.get("Threads_running"))
                global_threads_connected = safe_int(status.get("Threads_connected"))

                # 只在 GLOBAL STATUS 无效时才使用 PROCESSLIST（可能受权限限制）
                visible_threads_running = safe_int(process_stats[1]) if process_stats else 0
                visible_threads_connected = safe_int(process_stats[0]) if process_stats else 0

                # 优先使用全局状态值，只在为 0 时才考虑可见连接数
                threads_running = global_threads_running if global_threads_running > 0 else visible_threads_running
                threads_connected = global_threads_connected if global_threads_connected > 0 else visible_threads_connected

                # 调试日志：记录连接数采集情况
                if threads_connected == 0 or threads_running == 0:
                    logger.warning(
                        f"MySQL connection metrics may be incorrect - "
                        f"global: connected={global_threads_connected}, running={global_threads_running}; "
                        f"visible: connected={visible_threads_connected}, running={visible_threads_running}; "
                        f"final: connected={threads_connected}, running={threads_running}"
                    )

                return {
                    "connections_active": threads_running,
                    "connections_total": threads_connected,
                    "max_connections": max_connections,
                    "process_count": process_count,
                    "threads_running": threads_running,
                    "threads_connected": threads_connected,
                    "uptime": int(status.get("Uptime", 0)),
                    "slow_queries": int(status.get("Slow_queries", 0)),
                    "open_tables": int(status.get("Open_tables", 0)),
                    # 原始累积值 - 供 MetricNormalizer 计算实时速率
                    "questions": int(status.get("Questions", 0)),
                    "com_commit": int(status.get("Com_commit", 0)),
                    "com_rollback": int(status.get("Com_rollback", 0)),
                    "com_select": int(status.get("Com_select", 0)),
                    "com_insert": int(status.get("Com_insert", 0)),
                    "com_update": int(status.get("Com_update", 0)),
                    "com_delete": int(status.get("Com_delete", 0)),
                    # 网络流量（累积值，供 normalizer 计算速率）
                    "bytes_received": int(status.get("Bytes_received", 0)),
                    "bytes_sent": int(status.get("Bytes_sent", 0)),
                    # InnoDB 缓冲池
                    "cache_hit_rate": self._calc_bp_hit_rate(status),
                    "buffer_pool_hit_rate": self._calc_bp_hit_rate(status),
                    # InnoDB 行操作（累积值）
                    "innodb_rows_read": int(status.get("Innodb_rows_read", 0)),
                    "innodb_rows_inserted": int(status.get("Innodb_rows_inserted", 0)),
                    "innodb_rows_updated": int(status.get("Innodb_rows_updated", 0)),
                    "innodb_rows_deleted": int(status.get("Innodb_rows_deleted", 0)),
                    # InnoDB 磁盘 IO（累积值，供 normalizer 计算速率）
                    "innodb_data_reads": int(status.get("Innodb_data_reads", 0)),
                    "innodb_data_writes": int(status.get("Innodb_data_writes", 0)),
                    # 锁相关
                    "innodb_row_lock_waits": int(status.get("Innodb_row_lock_waits", 0)),
                    "innodb_row_lock_time": int(status.get("Innodb_row_lock_time", 0)),
                    "table_locks_waited": int(status.get("Table_locks_waited", 0)),
                    # 连接异常
                    "aborted_connections": int(status.get("Aborted_connects", 0)),
                    "aborted_clients": int(status.get("Aborted_clients", 0)),
                    # 临时表
                    "created_tmp_tables": int(status.get("Created_tmp_tables", 0)),
                    "created_tmp_disk_tables": int(status.get("Created_tmp_disk_tables", 0)),
                    # 平均 QPS/TPS（基于 uptime 的全局平均值，作为备用）
                    "qps": round(int(status.get("Questions", 0)) / uptime, 2),
                    "tps": round(
                        (int(status.get("Com_commit", 0)) + int(status.get("Com_rollback", 0)))
                        / uptime, 2
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
        import aiomysql
        conn = await self._connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO "
                    "FROM information_schema.PROCESSLIST "
                    "ORDER BY TIME DESC",
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

    async def terminate_session(self, session_id: int) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            target_session_id = int(session_id)
            async with conn.cursor() as cur:
                await cur.execute(f"KILL {target_session_id}")
            return {
                "success": True,
                "session_id": target_session_id,
                "message": f"MySQL 会话 {target_session_id} 已终止",
            }
        finally:
            conn.close()

    async def cancel_query(self, session_id: int) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            target_session_id = int(session_id)
            async with conn.cursor() as cur:
                await cur.execute(f"KILL QUERY {target_session_id}")
            return {
                "success": True,
                "session_id": target_session_id,
                "message": f"MySQL 查询 {target_session_id} 已取消",
            }
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

    async def _register_execution_session(self, conn, execution_state) -> None:
        if execution_state is None:
            return

        async with conn.cursor() as cur:
            await cur.execute("SELECT CONNECTION_ID()")
            row = await cur.fetchone()

        execution_state.session_id = str(row[0]) if row and row[0] is not None else None
        if execution_state.cancel_requested:
            raise QueryCancelledError("查询已取消")

    async def execute_query(
        self,
        sql: str,
        max_rows: int = 1000,
        execution_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        import time
        # 使用普通连接，通过 SQL_SELECT_LIMIT 限制结果
        conn = await self._connect()
        try:
            await self._register_execution_session(conn, execution_state)
            async with conn.cursor() as cur:
                start = time.time()

                # 使用 SQL_SELECT_LIMIT 在服务器端限制结果行数
                # 这类似于 JDBC 的 statement.setMaxRows()
                await cur.execute(f"SET SQL_SELECT_LIMIT = {max_rows + 1}")
                try:
                    await cur.execute(sql)
                    elapsed = round((time.time() - start) * 1000, 2)

                    if cur.description:
                        columns = [d[0] for d in cur.description]
                        # 先获取结果，再重置 SQL_SELECT_LIMIT
                        fetched_rows = await cur.fetchall()
                        truncated = len(fetched_rows) > max_rows
                        visible_rows = fetched_rows[:max_rows]
                        result = {
                            "columns": columns,
                            "rows": [list(r) for r in visible_rows],
                            "row_count": len(visible_rows),
                            "execution_time_ms": elapsed,
                            "truncated": truncated,
                        }
                    else:
                        row_count = cur.rowcount if cur.rowcount >= 0 else 0
                        await conn.commit()
                        result = {
                            "columns": [],
                            "rows": [],
                            "row_count": row_count,
                            "execution_time_ms": elapsed,
                            "truncated": False,
                            "message": f"Query OK, {row_count} rows affected",
                        }
                    return result
                finally:
                    # 无论成功或失败，都要重置 SQL_SELECT_LIMIT
                    await cur.execute("SET SQL_SELECT_LIMIT = DEFAULT")

        except QueryCancelledError:
            raise
        except Exception as exc:
            if execution_state is not None and execution_state.cancel_requested:
                raise QueryCancelledError("查询已取消") from exc
            raise
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
        """Get current lock waits (compatible with MySQL 5.x and 8.0+)."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                # MySQL 8.0+ 使用 performance_schema.data_lock_waits
                try:
                    await cur.execute(
                        "SELECT r.ENGINE_TRANSACTION_ID AS waiting_trx, "
                        "r.THREAD_ID AS waiting_thread, "
                        "rt.trx_query AS waiting_query, "
                        "b.ENGINE_TRANSACTION_ID AS blocking_trx, "
                        "b.THREAD_ID AS blocking_thread "
                        "FROM performance_schema.data_lock_waits w "
                        "JOIN performance_schema.data_locks r ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID "
                        "JOIN performance_schema.data_locks b ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID "
                        "LEFT JOIN information_schema.INNODB_TRX rt ON rt.trx_id = r.ENGINE_TRANSACTION_ID "
                        "LIMIT 50"
                    )
                    rows = await cur.fetchall()
                    return [{"waiting_trx": r[0], "waiting_thread": r[1], "waiting_query": r[2],
                             "blocking_trx": r[3], "blocking_thread": r[4]} for r in rows]
                except Exception:
                    pass

                # MySQL 5.x 回退到 information_schema.INNODB_LOCK_WAITS
                try:
                    await cur.execute(
                        "SELECT r.trx_id waiting_trx, r.trx_mysql_thread_id waiting_thread, "
                        "r.trx_query waiting_query, b.trx_id blocking_trx, b.trx_mysql_thread_id blocking_thread "
                        "FROM information_schema.INNODB_LOCK_WAITS w "
                        "JOIN information_schema.INNODB_TRX b ON b.trx_id = w.blocking_trx_id "
                        "JOIN information_schema.INNODB_TRX r ON r.trx_id = w.requesting_trx_id"
                    )
                    rows = await cur.fetchall()
                    return [{"waiting_trx": r[0], "waiting_thread": r[1], "waiting_query": r[2],
                             "blocking_trx": r[3], "blocking_thread": r[4]} for r in rows]
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

    async def get_top_sql(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get TOP SQL statistics from performance_schema."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                def _enabled(value: Any) -> bool:
                    text = str(value or "").strip().lower()
                    return text in {"1", "on", "yes", "true", "enabled"}

                # 检查 performance_schema 是否启用
                await cur.execute("SHOW VARIABLES LIKE 'performance_schema'")
                ps_row = await cur.fetchone()
                if not ps_row or not _enabled(ps_row[1]):
                    raise RuntimeError("当前实例未启用 performance_schema，无法获取 TOP SQL。")

                # 尝试校验 digest 汇总消费者是否开启（低权限账号可能无 setup_consumers 的读取权限）
                try:
                    await cur.execute(
                        "SELECT NAME, ENABLED FROM performance_schema.setup_consumers "
                        "WHERE NAME IN ('events_statements_summary_by_digest', 'statements_digest')"
                    )
                    consumer_rows = await cur.fetchall()
                    consumer_status = {str(row[0]).strip().lower(): _enabled(row[1]) for row in consumer_rows or []}
                    if (
                        "events_statements_summary_by_digest" in consumer_status
                        and not consumer_status["events_statements_summary_by_digest"]
                    ) or (
                        "statements_digest" in consumer_status
                        and not consumer_status["statements_digest"]
                    ):
                        raise RuntimeError(
                            "performance_schema 已开启，但 digest 统计消费者未启用。"
                            "请执行：UPDATE performance_schema.setup_consumers "
                            "SET ENABLED='YES' WHERE NAME IN "
                            "('events_statements_summary_by_digest','statements_digest');"
                        )
                except Exception as e:
                    err = str(e).lower()
                    if (
                        "setup_consumers" in err
                        and ("command denied" in err or "access denied" in err or "permission denied" in err)
                    ):
                        # 无权限时跳过消费者检查，继续尝试读取 digest 汇总表
                        pass
                    else:
                        raise

                # 兼容不同 MySQL 版本字段差异（如 AVG_ROWS_EXAMINED 可能不存在）
                await cur.execute(
                    "SELECT COLUMN_NAME "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = 'performance_schema' "
                    "AND TABLE_NAME = 'events_statements_summary_by_digest'"
                )
                digest_columns = {str(row[0]).upper() for row in (await cur.fetchall() or [])}
                if not digest_columns:
                    raise RuntimeError(
                        "未找到 performance_schema.events_statements_summary_by_digest，"
                        "可能你的数据库版本太老或者是不兼容的标准mysql版本，请确认实例版本与 performance_schema 配置。"
                    )

                has_sum_timer_wait = "SUM_TIMER_WAIT" in digest_columns
                has_sum_rows_examined = "SUM_ROWS_EXAMINED" in digest_columns
                has_sum_lock_time = "SUM_LOCK_TIME" in digest_columns
                has_avg_timer_wait = "AVG_TIMER_WAIT" in digest_columns
                has_avg_rows_examined = "AVG_ROWS_EXAMINED" in digest_columns
                has_avg_lock_time = "AVG_LOCK_TIME" in digest_columns
                has_last_seen = "LAST_SEEN" in digest_columns
                has_first_seen = "FIRST_SEEN" in digest_columns

                total_time_expr = (
                    "ROUND(SUM_TIMER_WAIT / 1000000000000, 6)"
                    if has_sum_timer_wait else
                    "0"
                )
                total_rows_expr = (
                    "ROUND(SUM_ROWS_EXAMINED, 0)"
                    if has_sum_rows_examined else
                    "0"
                )
                total_wait_expr = (
                    "ROUND(SUM_LOCK_TIME / 1000000000000, 6)"
                    if has_sum_lock_time else
                    "0"
                )
                avg_time_expr = (
                    "ROUND(AVG_TIMER_WAIT / 1000000000000, 6)"
                    if has_avg_timer_wait else
                    (
                        "ROUND((SUM_TIMER_WAIT / GREATEST(COUNT_STAR, 1)) / 1000000000000, 6)"
                        if has_sum_timer_wait else
                        "0"
                    )
                )
                avg_rows_expr = (
                    "ROUND(AVG_ROWS_EXAMINED, 2)"
                    if has_avg_rows_examined else
                    (
                        "ROUND(SUM_ROWS_EXAMINED / GREATEST(COUNT_STAR, 1), 2)"
                        if has_sum_rows_examined else
                        "0"
                    )
                )
                avg_wait_expr = (
                    "ROUND(AVG_LOCK_TIME / 1000000000000, 6)"
                    if has_avg_lock_time else
                    (
                        "ROUND((SUM_LOCK_TIME / GREATEST(COUNT_STAR, 1)) / 1000000000000, 6)"
                        if has_sum_lock_time else
                        "0"
                    )
                )
                last_exec_expr = (
                    "FROM_UNIXTIME(UNIX_TIMESTAMP(LAST_SEEN))"
                    if has_last_seen else
                    ("FROM_UNIXTIME(UNIX_TIMESTAMP(FIRST_SEEN))" if has_first_seen else "NULL")
                )
                order_expr = "SUM_TIMER_WAIT DESC" if has_sum_timer_wait else "COUNT_STAR DESC"

                # 从 events_statements_summary_by_digest 获取 SQL 统计
                await cur.execute(f"""
                    SELECT
                        DIGEST_TEXT as sql_text,
                        DIGEST as sql_id,
                        COUNT_STAR as exec_count,
                        {total_time_expr} as total_time_sec,
                        {total_rows_expr} as total_rows_scanned,
                        {total_wait_expr} as total_wait_time_sec,
                        {avg_time_expr} as avg_time_sec,
                        {avg_rows_expr} as avg_rows_scanned,
                        {avg_wait_expr} as avg_wait_time_sec,
                        {last_exec_expr} as last_exec_time
                    FROM performance_schema.events_statements_summary_by_digest
                    WHERE DIGEST_TEXT IS NOT NULL
                    ORDER BY {order_expr}
                    LIMIT {int(limit)}
                """)
                rows = await cur.fetchall()
                if not rows:
                    raise RuntimeError(
                        "未采集到 TOP SQL 数据。请先在实例上执行一段业务 SQL，"
                        "并确认账号具备 performance_schema 读取权限。"
                    )
                return [
                    {
                        "sql_text": r[0],
                        "sql_id": r[1],
                        "exec_count": int(r[2] or 0),
                        "total_time_sec": float(r[3] or 0),
                        "total_rows_scanned": int(r[4] or 0),
                        "total_wait_time_sec": float(r[5] or 0),
                        "avg_time_sec": float(r[6] or 0),
                        "avg_rows_scanned": float(r[7] or 0),
                        "avg_wait_time_sec": float(r[8] or 0),
                        "last_exec_time": str(r[9]) if r[9] else None,
                    }
                    for r in rows
                ]
        except RuntimeError:
            raise
        except Exception as e:
            import logging
            err = str(e)
            err_lower = err.lower()
            if "access denied" in err_lower or "permission denied" in err_lower:
                raise RuntimeError(
                    f"读取 performance_schema 权限不足，请为监控账号授予对应读取权限。原始错误: {err}"
                ) from e
            if "unknown column" in err_lower:
                raise RuntimeError(
                    "当前数据库版本的 performance_schema 字段与 TOP SQL 查询不兼容，"
                    f"请升级版本或调整采集 SQL。原始错误: {err}"
                ) from e
            logging.getLogger(__name__).warning(f"Failed to get TOP SQL: {e}")
            raise RuntimeError(f"读取 MySQL TOP SQL 失败: {e}") from e
        finally:
            conn.close()

    async def explain_sql(self, sql_text: str) -> List[Dict[str, Any]]:
        """Get execution plan for SQL statement."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                # 使用 EXPLAIN FORMAT=JSON 获取详细执行计划
                await cur.execute(f"EXPLAIN FORMAT=JSON {sql_text}")
                row = await cur.fetchone()
                if row and row[0]:
                    import json
                    explain_json = json.loads(row[0])
                    return {"format": "json", "plan": explain_json}
                return {"format": "json", "plan": {}}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to explain SQL: {e}")
            raise
        finally:
            conn.close()


import aiomysql
