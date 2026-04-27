import asyncio
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector
from backend.services.asyncpg_query_executor import execute_asyncpg_query
from backend.services.query_execution_state import QueryCancelledError


class PostgreSQLConnector(DBConnector):
    """PostgreSQL database connector using asyncpg."""

    async def _connect(self):
        import asyncpg

        last_error = None
        for attempt in range(2):
            try:
                return await asyncpg.connect(
                    host=self.host, port=self.port,
                    user=self.username, password=self.password or "",
                    database=self.database or "postgres",
                    timeout=10,
                    ssl=False,
                )
            except TimeoutError as e:
                last_error = e
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                raise

        raise last_error

    async def test_connection(self) -> str:
        conn = await self._connect()
        try:
            row = await conn.fetchrow("SELECT version()")
            return row[0] if row else "unknown"
        finally:
            await conn.close()

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            stats = await conn.fetchrow(
                """SELECT 
                        sum(numbackends)::bigint as numbackends, 
                        sum(xact_commit)::bigint as xact_commit, 
                        sum(xact_rollback)::bigint as xact_rollback, 
                        sum(blks_read)::bigint as blks_read, 
                        sum(blks_hit)::bigint as blks_hit, 
                        sum(tup_returned)::bigint as tup_returned, 
                        sum(tup_fetched)::bigint as tup_fetched, 
                        sum(tup_inserted)::bigint as tup_inserted, 
                        sum(tup_updated)::bigint as tup_updated, 
                        sum(tup_deleted)::bigint as tup_deleted, 
                        sum(conflicts)::bigint as conflicts, 
                        sum(deadlocks)::bigint as deadlocks 
                    FROM pg_stat_database"""
            )
            activity = await conn.fetchrow(
                "SELECT count(*) as total, "
                "count(CASE WHEN state = 'active' THEN 1 END) as active, "
                "count(CASE WHEN state = 'idle' THEN 1 END) as idle, "
                "count(CASE WHEN wait_event_type IS NOT NULL AND wait_event_type NOT IN ('Client', 'Activity') THEN 1 END) as waiting "
                "FROM pg_stat_activity"
            )
            size = await conn.fetchrow(
                "SELECT sum(pg_database_size(datname)) as db_size FROM pg_database"
            )
            # Get database start time and max_connections
            start_time = await conn.fetchrow(
                "SELECT pg_postmaster_start_time() as start_time"
            )
            max_conn = await conn.fetchrow(
                "SELECT setting::int as max_conn FROM pg_settings WHERE name = 'max_connections'"
            )
            # 锁等待数
            lock_waiting = await conn.fetchrow(
                "SELECT count(*) as cnt FROM pg_stat_activity "
                "WHERE wait_event_type IS NOT NULL AND wait_event_type NOT IN ('Client', 'Activity')"
            )
            # 最长事务运行时间（秒）
            longest_tx = await conn.fetchrow(
                "SELECT EXTRACT(EPOCH FROM max(now() - xact_start))::int as seconds "
                "FROM pg_stat_activity "
                "WHERE xact_start IS NOT NULL AND state != 'idle' "
            )

            hit_rate = 0
            if stats:
                total = (stats["blks_hit"] or 0) + (stats["blks_read"] or 0)
                if total > 0:
                    hit_rate = round((stats["blks_hit"] / total) * 100, 2)

            # Calculate uptime in seconds
            uptime = 0
            if start_time and start_time["start_time"]:
                from datetime import datetime, timezone
                boot_time = start_time["start_time"]
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                uptime = int((now_utc - boot_time).total_seconds())

            return {
                "connections_active": activity["active"] if activity else 0,
                "connections_total": activity["total"] if activity else 0,
                "connections_idle": activity["idle"] if activity else 0,
                "connections_waiting": activity["waiting"] if activity else 0,
                "max_connections": max_conn["max_conn"] if max_conn else 0,
                "lock_waiting": lock_waiting["cnt"] if lock_waiting else 0,
                "longest_transaction_sec": longest_tx["seconds"] if longest_tx and longest_tx["seconds"] else 0,
                "xact_commit": stats["xact_commit"] if stats else 0,
                "xact_rollback": stats["xact_rollback"] if stats else 0,
                "cache_hit_rate": hit_rate,
                "tup_returned": stats["tup_returned"] if stats else 0,
                "tup_fetched": stats["tup_fetched"] if stats else 0,
                "tup_inserted": stats["tup_inserted"] if stats else 0,
                "tup_updated": stats["tup_updated"] if stats else 0,
                "tup_deleted": stats["tup_deleted"] if stats else 0,
                "blks_read": stats["blks_read"] if stats else 0,
                "blks_hit": stats["blks_hit"] if stats else 0,
                "deadlocks": stats["deadlocks"] if stats else 0,
                "conflicts": stats["conflicts"] if stats else 0,
                "db_size_bytes": size["db_size"] if size else 0,
                "uptime": uptime,
                "boot_time": start_time["start_time"].isoformat() if start_time and start_time["start_time"] else None,
            }
        finally:
            await conn.close()

    async def get_variables(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch("SHOW ALL")
            return {r["name"]: r["setting"] for r in rows}
        finally:
            await conn.close()

    async def get_process_list(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT pid, usename, client_addr, datname, state, "
                "query_start, wait_event_type, wait_event, query "
                "FROM pg_stat_activity "
                "ORDER BY query_start DESC NULLS LAST"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def terminate_session(self, session_id: int) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            target_session_id = int(session_id)
            row = await conn.fetchrow(
                "SELECT pg_terminate_backend($1) AS terminated",
                target_session_id,
            )
            terminated = bool(row["terminated"]) if row else False
            if not terminated:
                raise RuntimeError(f"PostgreSQL 会话 {target_session_id} 终止失败")
            return {
                "success": True,
                "session_id": target_session_id,
                "message": f"PostgreSQL 会话 {target_session_id} 已终止",
            }
        finally:
            await conn.close()

    async def cancel_query(self, session_id: int) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            target_session_id = int(session_id)
            row = await conn.fetchrow(
                "SELECT pg_cancel_backend($1) AS cancelled",
                target_session_id,
            )
            cancelled = bool(row["cancelled"]) if row else False
            if not cancelled:
                raise RuntimeError(f"PostgreSQL 查询 {target_session_id} 取消失败")
            return {
                "success": True,
                "session_id": target_session_id,
                "message": f"PostgreSQL 查询 {target_session_id} 已取消",
            }
        finally:
            await conn.close()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            try:
                rows = await conn.fetch(
                    "SELECT query, calls, total_exec_time, mean_exec_time, rows "
                    "FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20"
                )
                return [dict(r) for r in rows]
            except Exception:
                rows = await conn.fetch(
                    "SELECT pid, query, state, "
                    "EXTRACT(EPOCH FROM (now() - query_start)) as duration_sec "
                    "FROM pg_stat_activity WHERE state = 'active' "
                    "AND query NOT LIKE '%pg_stat_activity%' "
                    "ORDER BY query_start LIMIT 20"
                )
                return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def _register_execution_session(self, conn, execution_state) -> None:
        if execution_state is None:
            return

        row = await conn.fetchrow("SELECT pg_backend_pid() AS pid")
        execution_state.session_id = str(row["pid"]) if row and row["pid"] is not None else None
        if execution_state.cancel_requested:
            raise QueryCancelledError("查询已取消")

    async def execute_query(
        self,
        sql: str,
        max_rows: int = 1000,
        execution_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            await self._register_execution_session(conn, execution_state)
            return await execute_asyncpg_query(conn, sql, max_rows=max_rows, explain_uses_fetch=False)
        except QueryCancelledError:
            raise
        except Exception as exc:
            if execution_state is not None and execution_state.cancel_requested:
                raise QueryCancelledError("查询已取消") from exc
            raise
        finally:
            await conn.close()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {sql}")
            return {"plan": [dict(r) for r in rows]}
        finally:
            await conn.close()

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schemaname, relname, n_live_tup, n_dead_tup, "
                "seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del, "
                "pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(relname)) as total_size "
                "FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 50"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_replication_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn "
                "FROM pg_stat_replication"
            )
            if rows:
                return {"replicas": [dict(r) for r in rows]}
            return {"status": "not configured"}
        finally:
            await conn.close()

    async def get_db_size(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                "SELECT pg_database_size(current_database()) as total_size, "
                "current_database() as database"
            )
            return {
                "database": row["database"],
                "total_size_bytes": row["total_size"],
            }
        finally:
            await conn.close()

    async def get_schemas(self) -> List[str]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast') "
                "AND schema_name NOT LIKE 'pg_temp_%' AND schema_name NOT LIKE 'pg_toast_temp_%' "
                "ORDER BY schema_name"
            )
            return [row["schema_name"] for row in rows]
        finally:
            await conn.close()

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            target_schema = schema or "public"
            rows = await conn.fetch(
                "SELECT table_name, table_type "
                "FROM information_schema.tables "
                "WHERE table_schema = $1 "
                "ORDER BY table_name",
                target_schema
            )
            return [
                {
                    "name": row["table_name"],
                    "schema": target_schema,
                    "type": row["table_type"],
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            target_schema = schema or "public"
            rows = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default, "
                "udt_name, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = $2 "
                "ORDER BY ordinal_position",
                target_schema, table
            )
            return [
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["column_default"],
                    "udt_name": row["udt_name"],
                    "max_length": row["character_maximum_length"],
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def get_index_stats(self) -> List[Dict[str, Any]]:
        """Get index usage statistics."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schemaname, relname as tablename, indexrelname as indexname, idx_scan, idx_tup_read, idx_tup_fetch "
                "FROM pg_stat_user_indexes ORDER BY idx_scan DESC LIMIT 50"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_lock_waits(self) -> List[Dict[str, Any]]:
        """Get current lock waits."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT blocked.pid AS blocked_pid, blocked.query AS blocked_query, "
                "blocking.pid AS blocking_pid, blocking.query AS blocking_query "
                "FROM pg_stat_activity AS blocked "
                "JOIN pg_stat_activity AS blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid)) "
                "WHERE blocked.pid != blocking.pid"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_table_fragmentation(self) -> List[Dict[str, Any]]:
        """Get table bloat/fragmentation info."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schemaname, relname as tablename, n_dead_tup, n_live_tup, "
                "CASE WHEN n_live_tup > 0 THEN ROUND(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2) ELSE 0 END as dead_ratio "
                "FROM pg_stat_user_tables WHERE n_dead_tup > 1000 ORDER BY n_dead_tup DESC LIMIT 20"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_top_sql(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get TOP SQL statistics from pg_stat_statements."""
        conn = await self._connect()
        try:
            extension_row = await conn.fetchrow(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') AS installed"
            )
            if not extension_row or not extension_row["installed"]:
                raise RuntimeError(
                    "当前连接的数据库未安装 pg_stat_statements 扩展，请在该库执行 CREATE EXTENSION pg_stat_statements。"
                )

            try:
                wait_time_column_row = await conn.fetchrow(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'pg_stat_statements'
                          AND column_name = 'blk_read_time'
                    ) AS has_blk_time
                    """
                )
                has_blk_time = bool(wait_time_column_row and wait_time_column_row["has_blk_time"])
                total_wait_expr = (
                    "ROUND(((blk_read_time + blk_write_time) / 1000)::numeric, 6)"
                    if has_blk_time else
                    "NULL::numeric"
                )
                avg_wait_expr = (
                    "ROUND((((blk_read_time + blk_write_time) / GREATEST(calls, 1) / 1000)::numeric), 6)"
                    if has_blk_time else
                    "NULL::numeric"
                )

                rows = await conn.fetch(f"""
                        SELECT
                            query as sql_text,
                            queryid::text as sql_id,
                            calls as exec_count,
                            ROUND((total_exec_time / 1000)::numeric, 6) as total_time_sec,
                            rows as total_rows_scanned,
                            {total_wait_expr} as total_wait_time_sec,
                            ROUND((mean_exec_time / 1000)::numeric, 6) as avg_time_sec,
                            ROUND((rows::numeric / GREATEST(calls, 1)::numeric), 2) as avg_rows_scanned,
                            {avg_wait_expr} as avg_wait_time_sec,
                            NULL as last_exec_time
                        FROM pg_stat_statements
                        WHERE query IS NOT NULL
                        ORDER BY total_exec_time DESC
                        LIMIT {int(limit)}
                    """)
                return [dict(r) for r in rows]
            except Exception as e:
                err = str(e)
                err_lower = err.lower()
                if "must be loaded via shared_preload_libraries" in err_lower:
                    raise RuntimeError(
                        "实例未启用 shared_preload_libraries=pg_stat_statements，请修改配置并重启数据库。"
                    ) from e
                if "permission denied" in err.lower():
                    raise RuntimeError(
                        "查询 pg_stat_statements 权限不足，请为监控账号授予 pg_read_all_stats 或使用更高权限账号。"
                    ) from e
                raise RuntimeError(f"读取 pg_stat_statements 失败: {err}") from e
        finally:
            await conn.close()

    async def explain_sql(self, sql_text: str) -> Dict[str, Any]:
        """Get execution plan for SQL statement."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(f"EXPLAIN (FORMAT JSON, ANALYZE FALSE) {sql_text}")
            if rows and len(rows) > 0:
                import json
                explain_json = json.loads(rows[0][0])
                return {"format": "json", "plan": explain_json}
            return {"format": "json", "plan": {}}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to explain SQL: {e}")
            raise
        finally:
            await conn.close()
